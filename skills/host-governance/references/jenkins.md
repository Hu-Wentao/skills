# Jenkins Host Management

Use this reference for Jenkins installation, upgrades, controller and agent
configuration, security, credentials, plugins, jobs, backups, and mobile
packaging. Jenkins is shared host infrastructure. Application source,
identity, signing intent, and build requirements remain authoritative in each
consuming project.

## Contents

- [Establish authority](#establish-authority)
- [Inspect before changing](#inspect-before-changing)
- [Install or upgrade Jenkins](#install-or-upgrade-jenkins)
- [Secure and operate the controller](#secure-and-operate-the-controller)
- [Manage plugins, nodes, and credentials](#manage-plugins-nodes-and-credentials)
- [Manage jobs through the API](#manage-jobs-through-the-api)
- [Configure Android packaging](#configure-android-packaging)
- [Configure iOS packaging](#configure-ios-packaging)
- [Diagnose and accept builds](#diagnose-and-accept-builds)
- [Back up and recover](#back-up-and-recover)

## Establish authority

Keep these ownership boundaries explicit:

| State | Authority |
| --- | --- |
| Controller package/image, Java runtime, service manager, storage, ports, reverse proxy, TLS, plugins, nodes, credentials, backups, and job runtime | Host infrastructure repository |
| Source repository, branch policy, application ID, Bundle ID, build variants, deployment environment, and required artifacts | Consuming project |
| Certificates, provisioning profiles, keystores, and signing policy | Approved signing authority or secret store |
| Current builds, queues, executors, nodes, and installed plugin state | Live Jenkins controller |

Do not copy host inventory, credentials, project identifiers, signing assets,
or job-specific values into this reusable skill. Resolve them at runtime from
their authority. Reconcile repository intent with live state before planning a
write.

## Inspect before changing

Record a timestamped baseline:

- operating system, architecture, service manager or container runtime;
- Jenkins version and distribution channel;
- Java vendor and supported major version;
- controller URL, bind address, reverse proxy, TLS termination, and health;
- Jenkins home, workspace, artifact, log, and backup storage;
- authentication realm, authorization strategy, CSRF protection, and anonymous
  permissions;
- installed plugins, versions, enabled state, dependency warnings, and pending
  restart;
- controller executors, agents, labels, tools, offline state, and capacity;
- credential IDs and scopes without secret values;
- queue, running builds, quiet-down state, and affected jobs.

Use product APIs, service-manager inspection, package metadata, and filesystem
metadata as separate evidence. Do not print environment dumps, Jenkins secret
files, credential payloads, private keys, tokens, or complete private job
configuration.

## Install or upgrade Jenkins

1. Resolve the desired Jenkins version or approved update channel, supported
   Java runtime, installation form, persistent data location, controller URL,
   ingress, and backup target from host-owned declarations.
2. Validate operating-system, filesystem, memory, disk, file-descriptor,
   network, DNS, TLS, and reverse-proxy prerequisites.
3. For an existing controller, quiet it down, wait for or deliberately abort
   builds according to policy, and create a restorable backup before changing
   the package, image, Java runtime, plugins, or Jenkins home.
4. Pin packages or image digests and plugin versions when reproducibility is
   required. Never upgrade the controller, Java, and all plugins blindly in
   one unbounded step.
5. Install or update through the host's governed package, container, or service
   workflow. Keep service ownership, permissions, limits, restart policy,
   health checks, and log rotation explicit.
6. Bootstrap security and configuration through reviewed automation or Jenkins
   Configuration as Code when the environment supports it. Keep secrets in an
   approved secret store and inject them only at execution time.
7. Verify startup, login, API authentication, CSRF crumbs, plugin dependency
   health, nodes, queue execution, a bounded test job, reverse proxy, TLS, and
   restart persistence before accepting the change.

Plan controller, Java, and plugin compatibility together. If an upgrade cannot
be rolled back against the resulting Jenkins home format, state that before
the write and use a tested restore rather than a package downgrade.

## Secure and operate the controller

- Terminate TLS at the governed ingress or controller and set the canonical
  Jenkins URL consistently.
- Disable anonymous administrative or job-configuration access. Grant people,
  automation, folders, and agents only the permissions they need.
- Keep CSRF protection enabled. Use API tokens or approved machine credentials;
  do not embed a password or token in a URL, job XML, shell argument, repository,
  console excerpt, or report.
- Separate controller administration, job configuration, build triggering,
  credential use, and credential management permissions.
- Run builds on labeled agents when feasible. Do not use controller executors
  for untrusted or resource-heavy builds.
- Bound build concurrency, timeouts, retention, workspace cleanup, artifact
  retention, disk usage, and logs.
- Avoid `set -x` and `bash -x`; wrappers frequently contain keychain passwords,
  repository credentials, webhooks, or upload tokens.
- Treat script-console execution, arbitrary Groovy, plugin installation,
  credential mutation, and security-realm changes as high-impact writes with
  separate authorization.

## Manage plugins, nodes, and credentials

For plugins, capture the current version set and dependency graph, review
security and compatibility effects, stage bounded changes, restart only when
required, and verify jobs that depend on changed plugins. Preserve a recovery
path for the controller and plugin directory.

For agents, verify identity, transport, trust, labels, toolchains, workspace,
executors, resource limits, clock, connectivity, and reconnect behavior. A
connected agent is not accepted until a representative bounded build runs on
the intended label.

For credentials, manage stable non-secret IDs and scopes in host declarations;
keep values in Jenkins or an approved external secret store. Verify that jobs
reference credential IDs rather than raw values. Rotate without printing the
old or new value, and test the narrow consumer before broader rollout.

## Manage jobs through the API

Use `scripts/jenkins_api.py` as a product adapter for job inspection,
comparison, configuration snapshots, view membership, and build triggering.
It reads credentials from environment variables by default:

```bash
export JENKINS_URL='https://jenkins.example.test'
export JENKINS_USER='api-user'
export JENKINS_API_TOKEN='token-from-secret-store'
```

Read-only examples:

```bash
uv run --script <skill-root>/scripts/jenkins_api.py inspect --job target-job
uv run --script <skill-root>/scripts/jenkins_api.py compare \
  --reference-job reference-job --target-job target-job
uv run --script <skill-root>/scripts/jenkins_api.py config-get \
  --job target-job --output /private/path/target-config.xml
```

The adapter never prints configuration XML, builder commands, credentials, or
build parameter values. `config-get` writes mode `0600`, refuses to overwrite,
and reports a SHA-256 digest.

Treat the adapter's `--authorized` flag as a mechanical safeguard only. Invoke
`config-create`, `config-update`, `view-add`, or `trigger` only through an
authorized host-governance operation and transaction. Before updating a job,
snapshot its exact XML and pass its current digest with
`--expected-current-sha256`; read back and verify the result.

Compare a reference job's structure before its values: job type, labels,
triggers, wrappers, parameters, builders, publishers, timeouts, cleanup, and
failure propagation. Replace source, identity, environment, signing, artifact,
upload, notification, and secret references from the target authorities.

## Configure Android packaging

Verify before the first build:

1. The job checks out the intended immutable commit or authorized branch.
2. Flutter, Gradle, JDK, Android SDK, and NDK versions satisfy the consuming
   project.
3. Dependency resolution and generated-code prerequisites are explicit.
4. Signing uses an approved credential reference, never raw keystore secrets.
5. The declared APK or AAB path and filename match the build command's actual
   output.
6. Missing output or failed upload makes the Jenkins result fail.

Require correct source identity, successful build, a nonempty expected
artifact, required delivery, and a final Jenkins `SUCCESS`.

## Configure iOS packaging

Treat signing and output as one keyed contract:

```text
(Bundle ID, Apple Team, distribution method)
  -> provisioning profile
  -> export-options mapping
  -> Jenkins environment
  -> actual IPA filename
```

Read the target Bundle ID from the target Xcode project or its governed product
source. Verify the profile's exact App ID, Team, certificate class,
distribution method, expiry, entitlements, and Ad Hoc device set when
applicable. Verify the export-options plist maps that Bundle ID to the profile
and intended Team and method.

Never make a target build green by changing its Bundle ID to another
application's identity. A reference application's profile proves only that
reference application can be exported. If target signing assets are missing,
keep the target identity intact and report the external signing blocker.

Do not assume the IPA is named `Runner.ipa`. Discover the actual export output,
then make rename, copy, archive, and upload steps use the same explicit artifact
contract.

## Diagnose and accept builds

Use read-only evidence first: job metadata, safe console matches,
configuration digests, archive `Info.plist`, decoded non-secret profile
metadata, export-options metadata, and artifact directory listings.

If a temporary job command is the only diagnostic channel:

1. ensure the job is idle;
2. snapshot exact config bytes and digest;
3. replace only the bounded command;
4. print no secrets;
5. restore the exact bytes in finally-equivalent cleanup;
6. verify the restored digest;
7. run a real build afterward so the latest result is honest.

Keep the acceptance gates distinct:

```text
source/build -> archive -> export -> artifact -> upload -> Jenkins result
```

Archive success is not export success. Export success is not artifact or
delivery success. A green build using another application's identity fails
acceptance.

## Back up and recover

Back up the configuration and state needed for the selected recovery objective,
including Jenkins home metadata, job definitions, plugin inventory, nodes,
credentials in their encrypted form with the matching controller keys, and any
external Configuration as Code or host declarations. Protect backups as
secrets, encrypt them, restrict access, define retention, and test restoration.

Before a mutation, record the target, exact snapshot or backup generation,
digest, Jenkins version, Java version, plugin set, transaction ID, and recovery
procedure. Afterward, verify both live behavior and restart persistence. A
backup that has never been restored is an unverified recovery claim.
