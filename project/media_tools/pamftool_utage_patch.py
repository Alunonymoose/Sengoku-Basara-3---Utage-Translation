#!/usr/bin/env python3
"""
Apply the BASARA Foundry Utage identity-preservation patch to PAMFtool v1.2.

Pinned upstream:
  https://github.com/ravenDS/PAMFtool
  commit 1559f643c660bfd1c14910354826c8f78b2000ec

Changes are deliberately narrow:
- add -m2v-pstd <KB>, preserving decoder-relevant MPEG-2 P-STD values;
- add -header-start-pts <ticks>, using PamfMuxer.StartPts90 instead of
  leaving the template's 90000 hardcoded;
- make the existing -initial-scr option actually affect pack-0 SCR.
  The upstream property is assigned by the CLI but WritePackedStream
  currently ignores it and hardcodes scr27=9216.

This script is fail-closed: every source replacement must match the pinned
upstream text exactly once.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PINNED_COMMIT = "1559f643c660bfd1c14910354826c8f78b2000ec"


def replace_once(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8-sig")
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {n}: {old[:100]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def require_commit(root: Path) -> None:
    try:
        got = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception as exc:
        raise RuntimeError(f"cannot resolve upstream git HEAD: {exc}") from exc
    if got != PINNED_COMMIT:
        raise RuntimeError(f"upstream drift: expected {PINNED_COMMIT}, got {got}")


def patch_program(root: Path) -> None:
    p = root / "PAMFtool" / "Program.vb"

    replace_once(
        p,
        """        Dim overridePstdKb As Integer = 0
        ' -mmb <n> : override max_mean_bitrate in AVC codec_info byte 25
""",
        """        Dim overridePstdKb As Integer = 0
        ' -m2v-pstd <KB> : override MPEG-2 Video P-STD buffer size (KB)
        '                  0 = use upstream default
        Dim overrideM2vPstdKb As Integer = 0
        ' -mmb <n> : override max_mean_bitrate in AVC codec_info byte 25
""",
    )

    replace_once(
        p,
        """        Dim overrideInitialScr As Long = -1L
        Dim i As Integer = 0
""",
        """        Dim overrideInitialScr As Long = -1L
        ' -header-start-pts <ticks> : PAMF sequence/group start PTS in 90 kHz units
        '                             -1 = upstream template default (90000)
        Dim overrideHeaderStartPts As Long = -1L
        Dim i As Integer = 0
""",
    )

    replace_once(
        p,
        """                Case "-mmb", "--mmb", "/mmb"
""",
        """                Case "-m2v-pstd", "--m2v-pstd", "/m2v-pstd"
                    If i + 1 >= args.Length OrElse Not Integer.TryParse(args(i + 1), overrideM2vPstdKb) _
                       OrElse overrideM2vPstdKb <= 0 OrElse overrideM2vPstdKb > 8191 Then
                        Console.Error.WriteLine("Error: -m2v-pstd requires a positive integer in KB (1..8191).")
                        Environment.Exit(1)
                    End If
                    i += 1
                Case "-mmb", "--mmb", "/mmb"
""",
    )

    replace_once(
        p,
        """                Case "-h", "--help", "/?", "/h", "-?"
""",
        """                Case "-header-start-pts", "--header-start-pts", "/header-start-pts"
                    Dim v As Long
                    If i + 1 >= args.Length OrElse Not Long.TryParse(args(i + 1), v) Then
                        Console.Error.WriteLine("Error: -header-start-pts requires a non-negative 90 kHz tick value.")
                        Environment.Exit(1)
                    End If
                    If v < 0L OrElse v >= (1L << 48) Then
                        Console.Error.WriteLine("Error: -header-start-pts out of 48-bit range.")
                        Environment.Exit(1)
                    End If
                    overrideHeaderStartPts = v
                    i += 1
                Case "-h", "--help", "/?", "/h", "-?"
""",
    )

    replace_once(
        p,
        """            PamfMuxRunner.Run(positional, noEp, forceDeblock, forceNoDeblock, noAtsc, paceMbps,
                              overridePstdKb, overrideMmb, ps2FramesPerBlock, overrideMuxRateBps,
                              overrideStdDelayTicks, overrideInitialScr)
""",
        """            PamfMuxRunner.Run(positional, noEp, forceDeblock, forceNoDeblock, noAtsc, paceMbps,
                              overridePstdKb, overrideM2vPstdKb, overrideMmb, ps2FramesPerBlock, overrideMuxRateBps,
                              overrideStdDelayTicks, overrideInitialScr, overrideHeaderStartPts)
""",
    )

    replace_once(
        p,
        """        Console.WriteLine("        [-deblock | -nodeblock] [-pace <Mbps>] [-pstd <KB>] [-mmb <n>]")
        Console.WriteLine("        [-ps2-block <N>] [-muxrate <kbps>]")
""",
        """        Console.WriteLine("        [-deblock | -nodeblock] [-pace <Mbps>] [-pstd <KB>] [-m2v-pstd <KB>] [-mmb <n>]")
        Console.WriteLine("        [-ps2-block <N>] [-muxrate <kbps>] [-header-start-pts <ticks>]")
""",
    )

    replace_once(
        p,
        """        Console.WriteLine("  -pstd <KB>       Override AVC P-STD buffer size in KB (1..8191).")
        Console.WriteLine("                      Default is per-level (1505 for L3.1, 3703 for L4.1, etc).")
""",
        """        Console.WriteLine("  -pstd <KB>       Override AVC P-STD buffer size in KB (1..8191).")
        Console.WriteLine("                      Default is per-level (1505 for L3.1, 3703 for L4.1, etc).")
        Console.WriteLine("  -m2v-pstd <KB>   Override MPEG-2 Video P-STD buffer size in KB (1..8191).")
""",
    )

    replace_once(
        p,
        """        Console.WriteLine("  -initial-scr <tk>  Override SCR value at pack 0 (auto-detected)")
        Console.WriteLine("                     default: 30 for AVC High profile, 30030 for AVC Main/M2V")
""",
        """        Console.WriteLine("  -initial-scr <tk>  Override SCR base value at pack 0.")
        Console.WriteLine("                     default: 30 for AVC High profile, 30030 for AVC Main/M2V")
        Console.WriteLine("  -header-start-pts <tk>  Override PAMF sequence/group start_pts.")
""",
    )


def patch_mux_runner(root: Path) -> None:
    p = root / "PAMFtool" / "PamfMuxRunner.vb"

    replace_once(
        p,
        """                   overridePstdKb As Integer,
                   overrideMmb As Integer,
""",
        """                   overridePstdKb As Integer,
                   overrideM2vPstdKb As Integer,
                   overrideMmb As Integer,
""",
    )
    replace_once(
        p,
        """                   overrideStdDelayTicks As Integer,
                   overrideInitialScr As Long)
""",
        """                   overrideStdDelayTicks As Integer,
                   overrideInitialScr As Long,
                   overrideHeaderStartPts As Long)
""",
    )
    replace_once(
        p,
        """        If overridePstdKb > 0 Then Console.WriteLine($"  -pstd {overridePstdKb}: overriding AVC P-STD buffer size to {overridePstdKb} KB")
        If overrideMmb >= 0 Then Console.WriteLine($"  -mmb {overrideMmb}: overriding max_mean_bitrate byte to {overrideMmb}")
""",
        """        If overridePstdKb > 0 Then Console.WriteLine($"  -pstd {overridePstdKb}: overriding AVC P-STD buffer size to {overridePstdKb} KB")
        If overrideM2vPstdKb > 0 Then Console.WriteLine($"  -m2v-pstd {overrideM2vPstdKb}: overriding MPEG-2 Video P-STD buffer size to {overrideM2vPstdKb} KB")
        If overrideMmb >= 0 Then Console.WriteLine($"  -mmb {overrideMmb}: overriding max_mean_bitrate byte to {overrideMmb}")
""",
    )
    replace_once(
        p,
        """        If overrideInitialScr >= 0 Then Console.WriteLine($"  -initial-scr {overrideInitialScr}: SCR at pack 0 (Sony uses 30 for logos, 30030 for game content)")
""",
        """        If overrideInitialScr >= 0 Then Console.WriteLine($"  -initial-scr {overrideInitialScr}: SCR base at pack 0")
        If overrideHeaderStartPts >= 0 Then Console.WriteLine($"  -header-start-pts {overrideHeaderStartPts}: PAMF sequence/group start PTS")
""",
    )
    replace_once(
        p,
        """        BuildPamfFromFiles(files, outPath, noEp, forceDeblock, forceNoDeblock, noAtsc, paceMbps,
                           overridePstdKb, overrideMmb, ps2FramesPerBlock, overrideMuxRateBps,
                           overrideStdDelayTicks, overrideInitialScr)
""",
        """        BuildPamfFromFiles(files, outPath, noEp, forceDeblock, forceNoDeblock, noAtsc, paceMbps,
                           overridePstdKb, overrideM2vPstdKb, overrideMmb, ps2FramesPerBlock, overrideMuxRateBps,
                           overrideStdDelayTicks, overrideInitialScr, overrideHeaderStartPts)
""",
    )
    replace_once(
        p,
        """                                   overridePstdKb As Integer,
                                   overrideMmb As Integer,
""",
        """                                   overridePstdKb As Integer,
                                   overrideM2vPstdKb As Integer,
                                   overrideMmb As Integer,
""",
    )
    replace_once(
        p,
        """                                   overrideStdDelayTicks As Integer,
                                   overrideInitialScr As Long)
""",
        """                                   overrideStdDelayTicks As Integer,
                                   overrideInitialScr As Long,
                                   overrideHeaderStartPts As Long)
""",
    )
    replace_once(
        p,
        """        If overrideInitialScr >= 0L Then
            mux.PsMuxer.InitialScr = overrideInitialScr
        End If

        Dim userSetInitialScr As Boolean = (overrideInitialScr >= 0L)
""",
        """        If overrideInitialScr >= 0L Then
            mux.PsMuxer.InitialScr = overrideInitialScr
        End If
        If overrideHeaderStartPts >= 0L Then
            mux.StartPts90 = overrideHeaderStartPts
        End If

        Dim userSetInitialScr As Boolean = (overrideInitialScr >= 0L)
""",
    )
    replace_once(
        p,
        """                Case "mpeg2" : RegisterAndQueueM2v(mux, f, userSetInitialScr)
""",
        """                Case "mpeg2" : RegisterAndQueueM2v(mux, f, userSetInitialScr, overrideM2vPstdKb)
""",
    )
    replace_once(
        p,
        """    Private Sub RegisterAndQueueM2v(mux As PamfMuxer, f As MuxInput, userSetInitialScr As Boolean)
""",
        """    Private Sub RegisterAndQueueM2v(mux As PamfMuxer, f As MuxInput,
                                           userSetInitialScr As Boolean,
                                           overrideM2vPstdKb As Integer)
""",
    )
    replace_once(
        p,
        """        Dim ps As PamfMuxStream = mux.AddM2vStream(
            profileLevel:=seq.ProfileAndLevel,
            progressive:=prog,
            frameRateCode:=frameRateCode,
            widthPx:=seq.WidthPixels, heightPx:=seq.HeightPixels,
            colourPrimaries:=colourPrim,
            transferChars:=transferCh,
            matrixCoeffs:=matrixCoeff)

        Dim tickPerFrame As Long = CLng(90000.0 / fps)
""",
        """        Dim ps As PamfMuxStream = mux.AddM2vStream(
            profileLevel:=seq.ProfileAndLevel,
            progressive:=prog,
            frameRateCode:=frameRateCode,
            widthPx:=seq.WidthPixels, heightPx:=seq.HeightPixels,
            colourPrimaries:=colourPrim,
            transferChars:=transferCh,
            matrixCoeffs:=matrixCoeff)
        If overrideM2vPstdKb > 0 Then
            ps.PstdBufferSize = overrideM2vPstdKb
            mux.HeaderWriter.OverrideLastM2vPstd(overrideM2vPstdKb)
        End If

        Dim tickPerFrame As Long = CLng(90000.0 / fps)
""",
    )


def patch_muxer(root: Path) -> None:
    p = root / "PAMFtool" / "PamfMuxer.vb"
    replace_once(
        p,
        """            Dim hdr As Byte() = HeaderWriter.Build(CInt(numPacks), TotalDuration90, muxRateUnits, StdDelayBoundTicks)
""",
        """            Dim hdr As Byte() = HeaderWriter.Build(CInt(numPacks), TotalDuration90, muxRateUnits, StdDelayBoundTicks, StartPts90)
""",
    )


def patch_header_writer(root: Path) -> None:
    p = root / "PAMFtool" / "PamfHeaderWriter.vb"
    replace_once(
        p,
        """        ' override the max_mean_bitrate byte (codec_info[25]) on the last-added AVC stream
""",
        """        ' override the P-STD buffer size on the LAST-added MPEG-2 Video stream
        Public Sub OverrideLastM2vPstd(kb As Integer)
            For i As Integer = _streams.Count - 1 To 0 Step -1
                If _streams(i).StreamTypeByte = &H2 Then
                    _streams(i).PStdBufferRaw = CUShort((1 << 13) Or (kb And &H1FFF))
                    Return
                End If
            Next
        End Sub

        ' override the max_mean_bitrate byte (codec_info[25]) on the last-added AVC stream
""",
    )
    replace_once(
        p,
        """        Public Function Build(numPacks As Integer, totalDuration90 As Long,
                              muxRateUnits As Integer,
                              Optional stdDelayBoundTicks As Integer = 90000) As Byte()
""",
        """        Public Function Build(numPacks As Integer, totalDuration90 As Long,
                              muxRateUnits As Integer,
                              Optional stdDelayBoundTicks As Integer = 90000,
                              Optional startPts90 As Long = 90000L) As Byte()
""",
    )
    replace_once(
        p,
        """            Dim durLow As UInteger = CUInt(totalDuration90 And &HFFFFFFFFL)
            WriteU32BE(_header, &H5E, durLow)
            WriteU32BE(_header, &H7C, durLow)
""",
        """            Dim startHi As UShort = CUShort((startPts90 >> 32) And &HFFFFL)
            Dim startLow As UInteger = CUInt(startPts90 And &HFFFFFFFFL)
            WriteU16BE(_header, &H56, startHi)
            WriteU32BE(_header, &H58, startLow)
            WriteU16BE(_header, &H74, startHi)
            WriteU32BE(_header, &H76, startLow)

            Dim durLow As UInteger = CUInt(totalDuration90 And &HFFFFFFFFL)
            WriteU32BE(_header, &H5E, durLow)
            WriteU32BE(_header, &H7C, durLow)
""",
    )


def patch_ps_muxer(root: Path) -> None:
    p = root / "PAMFtool" / "Mpeg2PsMuxer.vb"
    replace_once(
        p,
        """            Dim scr27 As Long = 9216L
            Dim scr As Long = scr27 \ 300L
""",
        """            ' Honor InitialScr. Preserve Sony's observed fractional extension
            ' for the common SCR base 30; other explicit bases start at extension 0.
            Dim initialExt As Long = If(InitialScr = 30L, 216L, 0L)
            Dim scr27 As Long = InitialScr * 300L + initialExt
            Dim scr As Long = scr27 \ 300L
""",
    )

    # Preserve Sony MPEG-2 GOP/random-access boundaries. Upstream can swallow a
    # small RAP AU into the preceding PES via whole-AU or partial-next packing,
    # which drops that GOP's explicit PTS/system_header/private_stream_2 boundary.
    replace_once(
        p,
        """                    If Ps2FramesPerBlock > 0 AndAlso s.IsVideo AndAlso s.Codec <> PamfStreamType.MPEG2Video Then
                        If nextAuIdx Mod Ps2FramesPerBlock = 0 Then Exit While
                    End If
                    extras.Add(n)
""",
        """                    If Ps2FramesPerBlock > 0 AndAlso s.IsVideo AndAlso s.Codec <> PamfStreamType.MPEG2Video Then
                        If nextAuIdx Mod Ps2FramesPerBlock = 0 Then Exit While
                    End If
                    If s.Codec = PamfStreamType.MPEG2Video AndAlso n.IsRandomAccessPoint Then
                        Exit While
                    End If
                    extras.Add(n)
""",
    )

    replace_once(
        p,
        """                        Dim swallowsBlockStart As Boolean =
                            (Ps2FramesPerBlock > 0 AndAlso s.IsVideo AndAlso
                             s.Codec <> PamfStreamType.MPEG2Video AndAlso
                             (nextAuIdxAfterExtras Mod Ps2FramesPerBlock) = 0)
                        If Not swallowsBlockStart Then
                            partialNext = n
""",
        """                        Dim swallowsBlockStart As Boolean =
                            (Ps2FramesPerBlock > 0 AndAlso s.IsVideo AndAlso
                             s.Codec <> PamfStreamType.MPEG2Video AndAlso
                             (nextAuIdxAfterExtras Mod Ps2FramesPerBlock) = 0)
                        Dim swallowsM2vRap As Boolean =
                            (s.Codec = PamfStreamType.MPEG2Video AndAlso n.IsRandomAccessPoint)
                        If Not swallowsBlockStart AndAlso Not swallowsM2vRap Then
                            partialNext = n
""",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream_root", type=Path)
    ns = ap.parse_args()
    root = ns.upstream_root.resolve()
    require_commit(root)
    patch_program(root)
    patch_mux_runner(root)
    patch_muxer(root)
    patch_header_writer(root)
    patch_ps_muxer(root)
    print(f"patched PAMFtool {PINNED_COMMIT} for BASARA Utage identity-preserving mux")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
