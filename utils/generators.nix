{ lib, pkgs, ... }:

with builtins;
with lib;
{
  mkGenerators = system: 
    let 
      _pkgs = pkgs system;
    in {
      toCSSFile = file:
        let fileName = removeSuffix ".scss" (baseNameOf file);
            compiledStyles =
              _pkgs.runCommand "compileScssFile"
                { buildInputs = [ _pkgs.sass ]; } ''
                  mkdir "$out"
                  scss --sourcemap=none \
                       --no-cache \
                       --style compressed \
                       --default-encoding utf-8 \
                       "${file}" \
                       >>"$out/${fileName}.css"
                '';
        in "${compiledStyles}/${fileName}.css";

      toFilteredImage = imageFile: options:
        let result = "result.png";
            filteredImage =
              _pkgs.runCommand "filterWallpaper"
                { buildInputs = [ _pkgs.imagemagick ]; } ''
                  mkdir "$out"
                  convert ${options} ${imageFile} $out/${result}
                '';
        in "${filteredImage}/${result}";
    };
}
