{ ... }:
{
  home-manager.users.jack.programs.neovim.extraConfig = ''
    " Opens Git link for selected line or region in browser
    noremap <leader>gb  :Gbrowse<Enter>
    " Adding hunks with :Gstatus - https://vi.stackexchange.com/a/21410
    "  - Press "=" on an file (shows git diff)
    "  - Press "-" on a hunk or visual selection to stage/unstage
    "  - "cvc" to commit verbosely
    noremap <leader>gs  :Git<Enter>
    noremap <leader>gl  :Glog<Enter>
  '';
}
