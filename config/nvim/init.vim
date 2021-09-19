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

" File Browser
let g:netrw_liststyle = 3
let g:netrw_banner = 0
let g:netrw_browse_split = 4
let g:netrw_winsize = 20
let g:netrw_altv = 20
noremap <leader>tf :Vexplore<Enter>
noremap <leader>r :Vifm<Enter>

" Fuzzy find
nnoremap <leader>F :Files<enter>
nnoremap <leader>G :Rg<enter>
nnoremap <leader>b :Buffers<enter>
nnoremap <leader>S :cex system("rg --column ")<Left><Left>

" Opens Git link for selected line or region in browser
noremap <leader>gb  :Gbrowse<Enter>
" Adding hunks with :Gstatus - https://vi.stackexchange.com/a/21410
"  - Press "=" on an file (shows git diff)
"  - Press "-" on a hunk or visual selection to stage/unstage
"  - "cvc" to commit verbosely
noremap <leader>gs  :Git<Enter>
noremap <leader>gl  :Glog<Enter>

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

  " Run black on save
  autocmd BufWritePre *.py execute ':Black'
augroup END

augroup terraformcmds
  " Run TerraformFmt on save
  autocmd BufWritePre *.tf execute ':TerraformFmt'
augroup END
