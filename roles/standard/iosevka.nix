{ pkgs, ... }:
let
  iosevka-fixed = pkgs.iosevka.override {
    set = "fixed";
    # private-build-plans.toml: Generated from https://typeof.net/Iosevka/customizer
    privateBuildPlan = ''
      [buildPlans.iosevka-fixed]
      family = "Iosevka Fixed"
      spacing = "fixed"
      serifs = "sans"
      no-cv-ss = true
    '';
  };
in
  iosevka-fixed
