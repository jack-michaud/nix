{ config, options, lib, pkgs, inputs, ... }:

with lib;
with lib.my;
let
  cfg = config.modules.dev.comment-trainer;
  comment-trainer = pkgs.buildGoModule {
    pname = "comment-trainer";
    version = inputs.comment-trainer.shortRev or "unstable";
    src = inputs.comment-trainer;
    # go.mod tracks Jack's local toolchain patch version, which can run ahead
    # of nixpkgs' go. The directive is only a minimum-toolchain marker, so pin
    # it to whatever go nixpkgs ships.
    postPatch = ''
      sed -i "s/^go .*/go ${pkgs.go.version}/" go.mod
    '';
    # The tree-sitter grammars #include C sources from outside their Go
    # package dirs, which `go mod vendor` prunes; the module cache keeps them.
    proxyVendor = true;
    vendorHash = "sha256-zV9MMjlgyDlZAFbRi7SRDlv2khzFs7IontMeR/vfQ4M=";
    nativeCheckInputs = [ pkgs.git ];  # e2e test shells out to git
  };
in {
  options.modules.dev.comment-trainer = {
    enable = mkBoolOpt false;
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      comment-trainer
    ];
  };
}
