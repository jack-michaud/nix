{ pkgs, ... }:
let
  iosevka-fixed = pkgs.iosevka.override {
    set = "fixed";
    # private-build-plans.toml: Generated from https://typeof.net/Iosevka/customizer
    privateBuildPlan = {
      family = "Iosevka Fixed";
      spacing = "fixed";
      serifs = "sans";
    };
  };
in
  iosevka-fixed
