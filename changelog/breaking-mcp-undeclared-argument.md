- A tool refuses an argument that it does not declare before it runs, whatever its value,
  and names the ones it takes, where the argument was dropped and the tool ran without it:
  `usda_wasde_get_table` called with `year` answers
  `error: InvalidRequestError: year: Not an argument of this tool; it takes table, month`
  and downloads nothing, where it read the latest release's page.
  (https://github.com/xippios/sdk-core/issues/84)
