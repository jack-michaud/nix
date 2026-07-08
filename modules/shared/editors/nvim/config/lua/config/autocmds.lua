-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
-- Add any additional autocmds here

-- :help cursorcolumn
vim.api.nvim_create_autocmd({'BufLeave'}, {
  callback = function ()
    vim.api.nvim_command("set nocursorline")
  end
})
vim.api.nvim_create_autocmd({'BufEnter'}, {
  callback = function ()
    vim.api.nvim_command("set cursorline")
  end
})

