---
slug: eagle
competitor: Autodesk Eagle
category: cad-electronics
left: kerf
right: eagle
hero_tagline: "Eagle democratised PCB design for a generation of makers — its successor lives inside Fusion, but Kerf gives you the same workflow without the subscription."
---

# Kerf vs Autodesk Eagle

Autodesk EAGLE (Easily Applicable Graphical Layout Editor) was for decades the default PCB design tool for hobbyists, startups, and small electronics teams. Cadsoft EAGLE, acquired by Autodesk in 2016, was notable for its affordable pricing, large part library (shared via Sparkfun and Adafruit footprint libraries), and a loyal community. Autodesk announced end-of-life for standalone EAGLE in 2023, with the final version 9.6.2 shipping June 2026. EAGLE's PCB workspace has been absorbed into Autodesk Fusion as "Fusion Electronics." This comparison covers both legacy EAGLE and its Fusion Electronics successor as a unit.

## Where they converge

Both EAGLE/Fusion Electronics and Kerf cover the core PCB design workflow: hierarchical schematic capture → netlist → PCB layout → Gerber / NC drill output. Both have component libraries, DRC, push-and-shove routing, and the ability to output industry-standard fabrication files. Both were (or are) popular with the maker and startup community — EAGLE defined that space, and Kerf targets it with a broader toolset.

Both tools also acknowledge MCAD/ECAD integration: EAGLE was integrated into Fusion specifically to provide a native PCB-to-mechanical link. Kerf has a co-resident MCAD+ECAD environment with IDF and STEP board export that achieves the same goal.

## Where Kerf wins

- **Not discontinued.** EAGLE end-of-life is June 2026. Kerf is an actively developed tool. If you are on EAGLE today, you are in migration mode — Kerf is one of the destinations worth evaluating.
- **In-box pre-compliance simulation.** EAGLE/Fusion Electronics provides basic DRC and SPICE simulation; signal integrity, EMC/EMI, PDN, and thermal analysis are extension-gated or not available. Kerf ships all four pre-compliance domains (SI: transmission-line, via stub, differential pair; EMC: common-mode, return-path gap, slot antenna; PDN: decap placement, target impedance, plane resonance; thermal: copper pour, via relief, hot-spot) without extension gating.
- **MIT open-core, no subscription.** EAGLE's free tier was 2-layer / 80cm²; Pro was ~$100/yr. Fusion Electronics is bundled in Fusion 360 at ~$680/yr (non-commercial personal use is more restricted). Kerf is MIT-licensed — free locally with no layer or board-size restriction.
- **Richer fab output.** Kerf exports Gerber 274X, Excellon NC drill, IPC-2581, ODB++, and IPC-D-356A netlist. EAGLE/Fusion's base fab pack covers Gerber/NC but not IPC-2581 or ODB++.
- **Multi-domain.** EAGLE was PCB-only. Fusion Electronics adds the MCAD link but keeps it within Autodesk's subscription. Kerf covers mechanical CAD, sheet metal, PCB, and pre-compliance simulation in a single MIT-licensed tool.

## Where EAGLE / Fusion Electronics wins

- **Part library legacy.** EAGLE's community has spent decades building component libraries (Sparkfun, Adafruit, component.guru, and thousands of shared .lbr files). This library ecosystem does not transfer to Kerf natively; Kerf's library is newer.
- **Fusion MCAD/ECAD live link.** Fusion Electronics has a native live bidirectional link between PCB placement and the Fusion mechanical model — move a component in the PCB editor and it moves in the 3D assembly. Kerf's MCAD/ECAD integration uses IDF and STEP export.
- **EAGLE muscle memory.** A decade of EAGLE users know the keybindings, command line, and ULP (EAGLE's scripting language) by heart. Moving to any other tool has friction.
- **Fusion's CAM and simulation.** If you already use Fusion for mechanical work, Fusion Electronics is already in your subscription — no additional cost. Kerf requires migrating the mechanical workflow too.
- **Community and tutorials.** EAGLE has Sparkfun tutorials, Adafruit guides, and YouTube walkthroughs numbering in the thousands. Kerf's electronics tutorial ecosystem is early-stage.

## Feature matrix

| Feature | Kerf | Autodesk EAGLE / Fusion Electronics |
|---|---|---|
| Status | Active development | EAGLE EOL June 2026; migrated to Fusion Electronics |
| License | MIT open-core | EAGLE proprietary (EOL); Fusion subscription ~$680/yr |
| Cost | Free local; hosted credits | Fusion: ~$680/yr (non-commercial personal is limited) |
| Schematic capture | Hierarchical schematic | Yes (EAGLE / Fusion Electronics) |
| PCB layout | Yes | Yes |
| Push-and-shove routing | Yes (shove router + FreeRouting) | Yes |
| Layer count | Unlimited | Unlimited (Fusion); EAGLE free was 2-layer |
| Board size limit | None | None (Fusion); EAGLE free was 80cm² |
| DRC | Yes + IPC-2221B presets | Yes |
| Gerber output | Yes | Yes |
| IPC-2581 output | Yes | No |
| ODB++ output | Yes | No |
| SPICE simulation | Yes + model lib + scikit-rf RF | Base SPICE (Fusion Electronics) |
| Signal integrity (SI) | In-box | Extension-gated or unavailable |
| EMC / EMI | In-box | Extension-gated or unavailable |
| PDN analysis | In-box | Extension-gated or unavailable |
| PCB thermal | In-box | Extension-gated (cooling analysis) |
| MCAD/ECAD link | Co-resident + IDF + STEP | Native Fusion live link |
| Part library | Growing | Large legacy EAGLE community library |
| Open source | Yes (MIT) | No |

## Both produce Gerber / IPC output

EAGLE, Fusion Electronics, and Kerf all produce Gerber RS-274X and Excellon NC drill files — the universal language of PCB fabrication. Any JLCPCB, PCBWay, or OSH Park order that ran on EAGLE Gerbers can run on Kerf Gerbers. IPC-2581 (which Kerf adds on top) is the next-generation unified data format that IPC is actively promoting as the Gerber successor.

---
*Last reviewed: 2026-05-19. EAGLE EOL announced by Autodesk; Fusion Electronics is the successor. Kerf capabilities reflect the current shipped product.*
