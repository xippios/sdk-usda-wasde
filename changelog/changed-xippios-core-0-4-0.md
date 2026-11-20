- Requires `xippios-core~=0.4.0`, from `~=0.3.0`, with its conventions 1.28, and
  `xippios-usda-esmis~=0.3.0`, from `~=0.1.0`. This package's tasks send the same requests
  and answer the same records through esmis 0.3. A caller that also calls esmis's own
  tasks takes esmis's changes since 0.1, among them `download_release_file` refusing a
  `dest` left out with `InvalidRequestError`.
  (https://github.com/xippios/sdk-core/releases/tag/v0.4.0,
  https://github.com/xippios/sdk-usda-esmis/releases/tag/v0.3.0)
