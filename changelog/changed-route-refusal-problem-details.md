- A route answers an argument that its schema refuses, a `get_table` without `table` or a
  `list_releases` whose `since` is no date, as problem details before the task runs: HTTP
  422, the title `InvalidRequestError` and the detail `<argument>: <message>`, such as
  `table: Field required`, where FastAPI's own 422 listed its error details with the
  input. (https://github.com/xippios/sdk-core/issues/66)
