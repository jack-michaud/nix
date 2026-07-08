
return {
  {
    "mfussenegger/nvim-lint",
    enabled = true,
    opts = {
      events = { "BufWritePost", "BufReadPost", "InsertLeave" },
      linters_by_ft = {
        python = { "mypy" },
      },
    },
    init = function()
      local mypy_config = require("lint").linters.mypy

      mypy_config.append_fname = false
      mypy_config.cmd = "poetry"
      mypy_config.args = {
        "run",
        "--",
        "dmypy",
        "run",
        "--",
        -- https://github.com/mfussenegger/nvim-lint/blob/master/lua/lint/linters/mypy.lua
        "--show-column-numbers",
        "--show-error-end",
        "--hide-error-context",
        "--no-color-output",
        "--no-error-summary",
        "--no-pretty",
        "--use-fine-grained-cache",
        ".",
      }
    end,
  },
}
