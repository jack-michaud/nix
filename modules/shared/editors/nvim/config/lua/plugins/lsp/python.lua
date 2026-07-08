
return {
  {
    "nvim-lspconfig",
    opts = {
      servers = {
        pyright = {
          settings = {
            python = {
              analysis = {
                diagnosticMode = "off",
                typeCheckingMode = "off"
              },
            },
          },
        },
        ruff_lsp = {},
      },
    },
  },
}

