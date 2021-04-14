{ lib, config, pkgs, options, ... }:
{

  networking.wireless.enable = true;  # Enables wireless support via wpa_supplicant.
  networking.wireless.userControlled.enable = true;
  networking.wireless.networks.TheFamilyHome_5G.pskRaw = "71cbf415156681914b4db0927f81bb83fc4e1816c312ca79d792607316b09057";

}

