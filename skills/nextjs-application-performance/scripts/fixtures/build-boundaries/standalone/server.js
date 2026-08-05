import http from "node:http";

http.createServer((request, response) => {
  response.statusCode = request.url === "/missing" ? 404 : 200;
  response.end("fixture");
}).listen(Number(process.env.PORT), process.env.HOSTNAME);
