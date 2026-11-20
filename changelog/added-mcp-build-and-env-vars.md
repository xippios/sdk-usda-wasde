- `xippios.usda.wasde.mcp.build()` returns the read-only tool set that
  `xippios-usda-wasde-mcp` serves, core's `ToolSet` with the caps of `tasks.MCP_CAPS`, so a
  host serves the eight WASDE tools beside other sources' in one server. `ENV_VARS`, beside
  `SOURCE`, names the variables the package reads: none, as the API is keyless.
  (https://github.com/xippios/sdk-core/issues/245,
  https://github.com/xippios/sdk-template/issues/81)
