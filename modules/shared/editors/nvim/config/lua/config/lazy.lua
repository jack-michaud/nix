local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"

-- Read protocol from environment, default to ssh
local git_protocol = os.getenv("NVIM_LAZY_GIT_PROTOCOL") or "ssh"
if git_protocol ~= "ssh" and git_protocol ~= "http" and git_protocol ~= "https" then
  git_protocol = "ssh"
end

-- Optional disable clone flag
local disable_clone = os.getenv("NVIM_LAZY_DISABLE_CLONE") == "1" or os.getenv("NVIM_LAZY_DISABLE_CLONE") == "true"

local function git_url(user, repo)
  if git_protocol == "http" or git_protocol == "https" then
    return string.format("https://github.com/%s/%s.git", user, repo)
  else
    return string.format("git@github.com:%s/%s.git", user, repo)
  end
end

if not disable_clone and not (vim.uv or vim.loop).fs_stat(lazypath) then
  local lazyrepo = git_url("folke", "lazy.nvim")
  local out = vim.fn.system({ "git", "clone", "--filter=blob:none", "--branch=stable", lazyrepo, lazypath })
  if vim.v.shell_error ~= 0 then
    vim.api.nvim_echo({
      { "Failed to clone lazy.nvim:\n", "ErrorMsg" },
      { out, "WarningMsg" },
      { "\nPress any key to exit..." },
    }, true, {})
    vim.fn.getchar()
    os.exit(1)
  end
end

vim.opt.rtp:prepend(vim.env.LAZY or lazypath)

local git_url_format
if git_protocol == "http" or git_protocol == "https" then
  git_url_format = "https://github.com/%s.git"
else
  git_url_format = "git@github.com:%s"
end

require("lazy").setup({
  spec = {
    { "LazyVim/LazyVim", import = "lazyvim.plugins" },
    { import = "lazyvim.plugins.extras.lang.python" },
    { import = "lazyvim.plugins.extras.linting.eslint" },
    { import = "lazyvim.plugins.extras.formatting.prettier" },
    { import = "lazyvim.plugins.extras.lang.json" },
    { import = "plugins" },
    { import = "plugins.formatting" },
    { import = "plugins.linting" },
    { import = "plugins.lsp" },
  },
  defaults = {
    lazy = false,
    version = false,
  },
  install = { colorscheme = { "tokyonight", "habamax" } },
  checker = { enabled = true },
  performance = {
    rtp = {
      disabled_plugins = {
        "gzip",
        "tarPlugin",
        "tohtml",
        "tutor",
        "zipPlugin",
      },
    },
  },
  git = {
    url_format = git_url_format,
  },
})
