-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

-- Always include a "desc" in the lua map with a short description of the keymap

function escape_to_json()
  local selected_text = vim.fn.getreg('"')
  local escaped_text = vim.fn.json_encode(selected_text)
  print(escaped_text)
end

-- Register as command `EscapeToJSON`
vim.cmd("command! EscapeToJSON :lua escape_to_json()")

function CreateTestFile()
  local current_file = vim.fn.expand("%:p")
  local test_file = string.gsub(current_file, "fay/", "tests/")
  -- Add `test_` prefix to the file base name.
  test_file = string.gsub(test_file, "([^/]+)$", "test_%1")
  vim.cmd("vsp " .. test_file)
end

vim.cmd("command! CreateTestFile :lua CreateTestFile()")

local function get_bufnr()
  return vim.api.nvim_get_current_buf()
end

function Get_filepath()
  local bufnr = get_bufnr()
  local full_path = vim.api.nvim_buf_get_name(bufnr)
  -- Get relative path
  local cwd = vim.fn.getcwd()
  local rel_path = vim.fn.fnamemodify(full_path, ":~:.")

  if string.find(rel_path, cwd, 1, true) == 1 then
    return string.sub(rel_path, #cwd + 2)
  end

  return rel_path
end
-- Hover
vim.keymap.set(
  "n",
  "<leader>h",
  "<cmd>lua vim.lsp.buf.hover()<CR>",
  { noremap = true, silent = true, desc = "LSP Hover" }
)

-- Go to definition
vim.keymap.set(
  "n",
  "<leader>.",
  "<cmd>lua vim.lsp.buf.definition()<CR>",
  { noremap = true, silent = true, desc = "LSP Go to definition" }
)

-- Find references
vim.keymap.set(
  "n",
  "<leader>,",
  "<cmd>lua vim.lsp.buf.references()<CR>",
  { noremap = true, silent = true, desc = "LSP Find references" }
)

-- Move selected text
vim.keymap.set("v", "J", ":m '>+1<CR>gv=gv")
vim.keymap.set("v", "K", ":m '<-2<CR>gv=gv")
