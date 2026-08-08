from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

import jenkins_api


CONFIG = b"""<?xml version="1.0" encoding="UTF-8"?>
<project>
  <disabled>false</disabled>
  <canRoam>true</canRoam>
  <concurrentBuild>false</concurrentBuild>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.StringParameterDefinition>
          <name>BUILD_NAME</name><defaultValue>1.0.0</defaultValue>
        </hudson.model.StringParameterDefinition>
        <hudson.model.ChoiceParameterDefinition>
          <name>BUILD_ENV</name>
          <choices><a><string>Android</string><string>iOS-Ad-Hoc</string></a></choices>
        </hudson.model.ChoiceParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
  <builders>
    <hudson.tasks.Shell><command>echo token=do-not-print\nflutter build ipa</command></hudson.tasks.Shell>
  </builders>
  <publishers/>
  <buildWrappers/>
</project>
"""


class Handler(BaseHTTPRequestHandler):
    config = CONFIG
    saw_auth = False

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes = b"", **headers: str) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = "Basic " + base64.b64encode(b"user:token").decode()
        Handler.saw_auth = self.headers.get("Authorization") == expected
        return Handler.saw_auth

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(401)
            return
        if self.path == "/crumbIssuer/api/json":
            self._send(
                200,
                json.dumps({"crumbRequestField": "Jenkins-Crumb", "crumb": "crumb"}).encode(),
                **{"Content-Type": "application/json"},
            )
        elif self.path == "/job/sample/config.xml":
            self._send(200, Handler.config, **{"Content-Type": "application/xml"})
        elif self.path.startswith("/job/sample/api/json"):
            self._send(
                200,
                json.dumps(
                    {
                        "name": "sample",
                        "color": "blue",
                        "buildable": True,
                        "inQueue": False,
                        "nextBuildNumber": 8,
                        "lastBuild": {"number": 7, "result": "SUCCESS", "duration": 1234},
                    }
                ).encode(),
                **{"Content-Type": "application/json"},
            )
        elif self.path == "/queue/item/1/api/json":
            self._send(
                200,
                json.dumps({"executable": {"number": 7}}).encode(),
                **{"Content-Type": "application/json"},
            )
        elif self.path.startswith("/job/sample/7/api/json"):
            self._send(
                200,
                json.dumps(
                    {
                        "building": False,
                        "result": "SUCCESS",
                        "duration": 1234,
                        "estimatedDuration": 1500,
                    }
                ).encode(),
                **{"Content-Type": "application/json"},
            )
        else:
            self._send(404)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401)
            return
        if self.headers.get("Jenkins-Crumb") != "crumb":
            self._send(403)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/job/sample/config.xml":
            Handler.config = body
            self._send(200)
        elif self.path == "/job/sample/buildWithParameters":
            self._send(201, Location="http://internal.invalid/queue/item/1/")
        else:
            self._send(404)


class ServerFixture:
    def __enter__(self) -> str:
        Handler.config = CONFIG
        Handler.saw_auth = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class JenkinsApiTests(unittest.TestCase):
    def test_redact_removes_url_and_assignment_secrets(self) -> None:
        value = jenkins_api.redact(
            "https://user:pass@example.test/a token=abc Authorization: Bearer xyz"
        )
        self.assertNotIn("user:pass", value)
        self.assertNotIn("abc", value)
        self.assertNotIn("xyz", value)
        self.assertIn("[REDACTED]", value)

    def test_config_summary_does_not_expose_builder_command(self) -> None:
        summary = jenkins_api.config_summary(CONFIG)
        encoded = json.dumps(summary)
        self.assertNotIn("do-not-print", encoded)
        self.assertEqual(["BUILD_NAME", "BUILD_ENV"], [p["name"] for p in summary["parameters"]])
        self.assertEqual(["Android", "iOS-Ad-Hoc"], summary["parameters"][1]["choices"])
        self.assertEqual(2, summary["builders"][0]["command_line_count"])

    def test_paths_and_parameters_are_deterministic(self) -> None:
        self.assertEqual("/job/folder/job/mobile", jenkins_api.job_path("folder/mobile"))
        self.assertEqual({"A": "1", "B": "x=y"}, jenkins_api.parse_params(["A=1", "B=x=y"]))
        with self.assertRaises(jenkins_api.JenkinsError):
            jenkins_api.parse_params(["A=1", "A=2"])

    def test_private_snapshot_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.xml"
            jenkins_api.write_private_snapshot(path, CONFIG)
            self.assertEqual(CONFIG, path.read_bytes())
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            with self.assertRaises(jenkins_api.JenkinsError):
                jenkins_api.write_private_snapshot(path, CONFIG)

    def test_inspect_update_and_trigger_against_fake_jenkins(self) -> None:
        with ServerFixture() as url:
            client = jenkins_api.JenkinsClient(url, "user", "token")
            inspected = jenkins_api.inspect_job(client, "sample")
            self.assertEqual("SUCCESS", inspected["last_build"]["result"])
            self.assertTrue(Handler.saw_auth)

            changed = CONFIG.replace(b"<disabled>false</disabled>", b"<disabled>true</disabled>")
            updated = jenkins_api.update_config(
                client, "sample", changed, jenkins_api.sha256_bytes(CONFIG)
            )
            self.assertEqual("true", updated["config"]["disabled"])

            result = jenkins_api.trigger_build(
                client,
                "sample",
                {"BUILD_ENV": "iOS-Ad-Hoc"},
                wait=True,
                timeout=2,
                poll_interval=0.001,
            )
            self.assertEqual("SUCCESS", result["result"])
            self.assertEqual(["BUILD_ENV"], result["parameter_names"])
            self.assertNotIn("iOS-Ad-Hoc", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
