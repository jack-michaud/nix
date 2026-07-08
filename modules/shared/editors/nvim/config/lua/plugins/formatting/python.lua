
return {
  {
    "stevearc/conform.nvim",
    -- https://github.com/stevearc/conform.nvim
    enabled = true,
    opts = function()
      return {
        formatters_by_ft = {
          python = {
            "ruff_format",
            "ruff_fix",
            "ruff_organize_imports",
          },
        },
      }
    end,
  },
}
