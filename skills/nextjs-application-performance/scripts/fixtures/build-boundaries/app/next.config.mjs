const serverPackages = new Set(["@fixture/server"]);

export default {
  output: "standalone",
  serverExternalPackages: [],
  webpack(config, { isServer }) {
    if (isServer) {
      config.externals.push(({ request }, callback) => {
        if (serverPackages.has(request) || [...serverPackages].some((name) => request.startsWith(`${name}/`))) {
          return callback(null, `module ${request}`);
        }
        return callback();
      });
    }
    return config;
  },
};
