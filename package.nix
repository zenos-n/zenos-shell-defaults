{ lib, stdenvNoCC, python3, makeWrapper, nix, nix-output-monitor }:
stdenvNoCC.mkDerivation {
  pname = "zenos-shell-defaults";
  version = "1.1.0";
  src = lib.cleanSource ./.;
  dontBuild = true;
  nativeBuildInputs = [ makeWrapper ];
  doCheck = true;
  checkPhase = ''
    PYTHONDONTWRITEBYTECODE=1 ${python3}/bin/python3 -m unittest discover -s tests -v
  '';
  installPhase = ''
    runHook preInstall
    install -Dm0644 resources/p10k.zsh "$out/share/zenos-shell/p10k.zsh"
    install -Dm755 scripts/nix-monitor.py "$out/libexec/zenos-nix-monitor"
    substituteInPlace "$out/libexec/zenos-nix-monitor" \
      --replace-fail '@nix@' '${nix}' \
      --replace-fail '@nom@' '${nix-output-monitor}'
    makeWrapper ${python3}/bin/python3 "$out/bin/zenos-nix" \
      --add-flags "$out/libexec/zenos-nix-monitor"
    ln -s zenos-nix "$out/bin/zenos-nix-monitor"
    runHook postInstall
  '';
  meta = {
    description = "ZenOS default Powerlevel10k shell configuration";
    platforms = lib.platforms.linux;
  };
}
