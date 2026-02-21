# Rádio IA News - Dependências de sistema (Nix)
# FFmpeg é necessário para o pydub processar MP3
{ pkgs }: {
  deps = [
    pkgs.ffmpeg
    pkgs.bashInteractive
  ];
}
