- `xippios-usda-wasde-mcp` names itself in its usage line and its errors, an unknown option
  ending `xippios-usda-wasde-mcp: error: unrecognized arguments: --bogus`, where they named
  the server, `xippios-usda-wasde`. Its help says that `--allow-remote` changes nothing on
  this read server, which is not held to loopback, where it spoke of a write server.
  (https://github.com/xippios/sdk-core/issues/167)
