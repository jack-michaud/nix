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
noremap <leader>r :Vexplore<Enter>

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

