{ lib, stdenvNoCC }:
stdenvNoCC.mkDerivation {
  pname = "zenos-shell-defaults";
  version = "1.0.0";
  src = lib.cleanSource ./.;
  dontBuild = true;
  installPhase = ''
    runHook preInstall
    install -Dm0644 resources/p10k.zsh "$out/share/zenos-shell/p10k.zsh"
    runHook postInstall
  '';
  meta = {
    description = "ZenOS default Powerlevel10k shell configuration";
    platforms = lib.platforms.linux;
  };
}
