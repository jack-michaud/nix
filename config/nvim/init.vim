set nocompatible
filetype off
set undofile

set number
set rnu
set tabstop=2
set softtabstop=2
set shiftwidth=2
set expandtab
set backspace=2
set hlsearch
set hidden

set ignorecase
set smartcase
set wildmode=longest,list,full

syntax on

set termguicolors
colorscheme monokai_pro

" Mouse control
set mouse=a

" https://thoughtbot.com/blog/faster-grepping-in-vim
" The Silver Searcher
if executable('ag')
  " Use ag over grep
  set grepprg=ag\ --nogroup\ --nocolor

  " Use ag in CtrlP for listing files. Lightning fast and respects    .gitignore
  let g:ctrlp_user_command = 'ag %s -l --nocolor -g ""'

  " ag is fast enough that CtrlP doesn't need to cache
  let g:ctrlp_use_caching = 0
endif

let mapleader = "`"
map <Space> <leader>

inoremap jk <Esc>

" Copy to clipboard
vnoremap  <leader>y  "+y
nnoremap  <leader>Y  "+yg_
nnoremap  <leader>y  "+y
nnoremap  <leader>yy  "+yy

" Paste from clipboard
nnoremap <leader>p "+p
nnoremap <leader>P "+P
vnoremap <leader>p "+p
vnoremap <leader>P "+P

" Telescope stuff
lua << EOF
local fb_actions = require("telescope").extensions.file_browser.actions
require('telescope').setup {
  extensions = {
    file_browser = {
      theme = 'dropdown',
      mappings = {
        ['i'] = {
          ['<C-t>'] = fb_actions.change_cwd,
          ['<C-r>'] = fb_actions.create,
        },
        ['n'] = {
        },
      },
    },
  },
}
require('telescope').load_extension('fzf')
require('telescope').load_extension('file_browser')
require('telescope').load_extension('gh')
EOF

"nnoremap <leader>r :Vifm<enter>
nnoremap <leader>r :Telescope file_browser<enter>
"nnoremap <leader>F :Files<enter>
nnoremap <leader>F :Telescope find_files<enter>
"nnoremap <leader>G :Rg<enter>
nnoremap <leader>G :Telescope live_grep<enter>
"nnoremap <leader>b :Buffers<enter>
nnoremap <leader>b :Telescope buffers<enter>
"nnoremap <leader>S :cex system("rg --column ")<Left><Left>
nnoremap <leader>H :Telescope help_tags<enter>

nnoremap <leader>S :cex system("rg --column ")<Left><Left>

" Opens Git link for selected line or region in browser
noremap <leader>gb  :GBrowse<Enter>
" Adding hunks with :Gstatus - https://vi.stackexchange.com/a/21410
"  - Press "=" on an file (shows git diff)
"  - Press "-" on a hunk or visual selection to stage/unstage
"  - "cvc" to commit verbosely
noremap <leader>gs  :Git<Enter>
noremap <leader>gl  :Gclog<Enter>

" LSP Stuff
"nmap <silent> <leader>h <Plug>(coc-hover)
"nmap <silent> <leader>. <Plug>(coc-definition)
"nmap <silent> <leader>, <Plug>(coc-references)
" Applying codeAction to the selected region.
" Example: `<leader>aap` for current paragraph
"xmap <leader>a  <Plug>(coc-codeaction)

"nmap <leader>R <Plug>(coc-rename)
"nmap <leader>cn <Plug>(coc-diagnostic-next)
"nmap <leader>cp <Plug>(coc-diagnostic-prev)

inoremap <expr> <cr> pumvisible() ? "\<C-y>" : "\<C-g>u\<CR>"

" Language specific
augroup pythoncmds
  "autocmd!
  autocmd FileType python nnoremap <buffer> <leader>g t[a.get(<Esc>lmz%a)<Esc>hx`zx?get<Enter>
  autocmd FileType python iabbrev <buffer> rr return
  autocmd FileType python iabbrev <buffer> argparser import argparse; parser = argparse.ArgumentParser()
  autocmd FileType python iabbrev <buffer> importpdb import pdb; pdb.set_trace()

augroup END


lua << EOF
local parser_install_dir = vim.fn.stdpath("cache") .. "/treesitters"

vim.fn.mkdir(parser_install_dir, "p")
vim.opt.runtimepath:append(parser_install_dir)

require('nvim-treesitter.configs').setup {
  -- One of "all", "maintained" (parsers with maintainers), or a list of languages
  ensure_installed = {"python", "typescript", "go", "haskell", "nix", "hcl", "dart"},

  parser_install_dir = parser_install_dir,
  
  -- Install languages synchronously (only applied to `ensure_installed`)
  sync_install = false,
  
  -- List of parsers to ignore installing
  ignore_install = { "javascript" },
  
  highlight = {
    -- `false` will disable the whole extension
    enable = true,
  
    -- list of language that will be disabled
    disable = { "c", "rust" },
    
    -- Setting this to true will run `:h syntax` and tree-sitter at the same time.
    -- Set this to `true` if you depend on 'syntax' being enabled (like for indentation).
    -- Using this option may slow down your editor, and you may see some duplicate highlights.
    -- Instead of true it can also be a list of languages
    additional_vim_regex_highlighting = false,
  },
}
EOF

lua << EOF
require('feline').setup()
EOF

lua << EOF
require('gitsigns').setup()
EOF

lua << EOF
local augroup = vim.api.nvim_create_augroup("LspFormatting", {})
require("null-ls").setup({
    sources = {
        require("null-ls").builtins.formatting.black,
        require("null-ls").builtins.formatting.dart_format.with({
          extra_args = {"--line-length=120"}
        }),
        require("null-ls").builtins.formatting.nixfmt,
        require("null-ls").builtins.formatting.gofmt,
        require("null-ls").builtins.formatting.phpcbf,
        require("null-ls").builtins.formatting.rustfmt,
        require("null-ls").builtins.formatting.terraform_fmt,

        require("null-ls").builtins.diagnostics.mypy,
    },
    on_attach = function(client)
        if client.supports_method("textDocument/formatting") then
            vim.api.nvim_clear_autocmds({ group = augroup, buffer = bufnr })
            vim.api.nvim_create_autocmd("BufWritePre", {
                group = augroup,
                buffer = bufnr,
                callback = function()
                    vim.lsp.buf.format({ 
                      bufnr = bufnr,
                      filter = function(client)
                        return client.name == "null-ls"
                      end
                    })
                end,
            })
        end
    end,
})
EOF

set completeopt=menu,menuone,noselect

lua << EOF


local cmp = require("cmp")
local has_words_before = function()
  if vim.api.nvim_buf_get_option(0, "buftype") == "prompt" then return false end
  local line, col = unpack(vim.api.nvim_win_get_cursor(0))
  return col ~= 0 and vim.api.nvim_buf_get_text(0, line-1, 0, line-1, col, {})[1]:match("^%s*$") == nil
end

cmp.setup({
  sources = cmp.config.sources({
    { name = "copilot", group_index = 1 },
    { name = "nvim_lsp", group_index = 2 },
    { name = "flutter-tools", group_index = 2}
  }),
  mapping = cmp.mapping.preset.insert({
    ["<CR>"] = cmp.mapping.confirm({ select = true }),
    ["<Tab>"] = cmp.mapping(function(fallback)
      if cmp.visible() then
        cmp.select_next_item()
      elseif has_words_before() then
        cmp.complete()
      else
        fallback()
      end
    end, { "i", "s" }),
    ["<S-Tab>"] = cmp.mapping(function()
      if cmp.visible() then
        cmp.select_prev_item()
      elseif vim.fn["vsnip#jumpable"](-1) == 1 then
        feedkey("<Plug>(vsnip-jump-prev)", "")
      end
    end, { "i", "s" }),
  }),
  window = {
    completion = cmp.config.window.bordered(),
    documentation = cmp.config.window.bordered(),
  }
})
local capabilities = require("cmp_nvim_lsp").update_capabilities(vim.lsp.protocol.make_client_capabilities())
local on_attach = function(client, bufnr)
  vim.keymap.set('n', '<space>.', vim.lsp.buf.definition, bufopts)
  vim.keymap.set('n', '<space>h', vim.lsp.buf.hover, bufopts)
  vim.keymap.set('n', '<space>i', vim.lsp.buf.implementation, bufopts)
  vim.keymap.set('n', '<space>R', vim.lsp.buf.rename, bufopts)
  vim.keymap.set('n', '<space>ca', vim.lsp.buf.code_action, bufopts)
  vim.keymap.set('n', '<space>,', vim.lsp.buf.references, bufopts)
end

require("lspconfig").pyright.setup{
  on_attach = on_attach,
  capabilities = capabilities,
}
require("lspconfig")["rust_analyzer"].setup{
  on_attach = on_attach,
  capabilities = capabilities,
}


local packer = require("packer")
packer.init({
  git = {
    default_url_format = "git@github.com:%s"
  }
})
packer.startup(function(use)
  use {
    "zbirenbaum/copilot.lua",
    event = {"VimEnter"},
    config = function()
      vim.defer_fn(function()
        require("copilot").setup()
      end, 100)
    end,
  }
  use {
    "zbirenbaum/copilot-cmp",
    after = {"copilot.lua"},
    requires = {"github/copilot.vim"},
    config = function()
      require("copilot_cmp").setup()
    end,
  }
  -- Not declaratively installed because this updates daily
  use {
    "mfussenegger/nvim-dap",
  }
  use {
    "williamboman/mason-lspconfig.nvim",
    requires = "williamboman/mason.nvim",
    config = function()
      require("mason").setup()
      require("mason-lspconfig").setup()
      vim.keymap.set('n', '<space>m', function() vim.cmd("Mason") end, bufopts)
    end
  }
  use {
    'akinsho/flutter-tools.nvim',
    after = {"nvim-dap"},
    requires = 'nvim-lua/plenary.nvim', 
    config = function()
      local on_attach = function(client, bufnr)
        vim.keymap.set('n', '<space>.', vim.lsp.buf.definition, bufopts)
        vim.keymap.set('n', '<space>h', vim.lsp.buf.hover, bufopts)
        vim.keymap.set('n', '<space>i', vim.lsp.buf.implementation, bufopts)
        vim.keymap.set('n', '<space>R', vim.lsp.buf.rename, bufopts)
        vim.keymap.set('n', '<space>ca', vim.lsp.buf.code_action, bufopts)
        vim.keymap.set('n', '<space>,', vim.lsp.buf.references, bufopts)
      end
      require("flutter-tools").setup{
        debugger = {
          enabled = true;
        },
        lsp = {
          on_attach = on_attach,
          capabilities = capabilities,
          color = {
            enabled = true,
            background = true,
            virtual_text = false,
          },
          settings = {
            showTodos = false,
            renameFilesWithClasses = "prompt",
            updateImportsOnRename = true,
            completeFunctionCalls = true,
            lineLength = 120,
          },
        },
        dev_log = { enabled = true },
      }
    end
  }
end)
EOF

