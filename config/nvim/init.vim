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
noremap <leader>gb  :Gbrowse<Enter>
" Adding hunks with :Gstatus - https://vi.stackexchange.com/a/21410
"  - Press "=" on an file (shows git diff)
"  - Press "-" on a hunk or visual selection to stage/unstage
"  - "cvc" to commit verbosely
noremap <leader>gs  :Git<Enter>
noremap <leader>gl  :Gclog<Enter>

"" Coc-snippets
" Use <C-l> for trigger snippet expand.
imap <C-l> <Plug>(coc-snippets-expand)

" Use <C-j> for select text for visual placeholder of snippet.
vmap <C-j> <Plug>(coc-snippets-select)

" Use <C-j> for jump to next placeholder, it's default of coc.nvim
let g:coc_snippet_next = '<c-j>'

" Use <C-k> for jump to previous placeholder, it's default of coc.nvim
let g:coc_snippet_prev = '<c-k>'

" Use <leader>x for convert visual selected code to snippet
xnoremap <leader>x  <Plug>(coc-convert-snippet)

" LSP Stuff
nmap <silent> <leader>. <Plug>(coc-definition)
nmap <silent> <leader>, <Plug>(coc-references)
" Applying codeAction to the selected region.
" Example: `<leader>aap` for current paragraph
xmap <leader>a  <Plug>(coc-codeaction-selected)

nmap <leader>R <Plug>(coc-rename)
nmap <leader>cn <Plug>(coc-diagnostic-next)
nmap <leader>cp <Plug>(coc-diagnostic-prev)

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
require('nvim-treesitter.configs').setup {
  -- One of "all", "maintained" (parsers with maintainers), or a list of languages
  ensure_installed = "maintained",
  
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
    },
    on_attach = function(client)
      if client.resolved_capabilities.document_formatting then
          vim.cmd([[
          augroup LspFormatting
            autocmd! * <buffer>
            autocmd BufWritePre <buffer> lua vim.lsp.buf.formatting_sync()

          ]])
      end
    end,
})
EOF
