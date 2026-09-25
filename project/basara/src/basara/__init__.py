"""basara -- the single core library for the Sengoku BASARA 3 Utage English patch.

One implementation per format, typed models, exact round trips, fail-closed
mutation. Every tool in the project should import from here.

    arc     MT Framework ARC v8 read / lenient inspect / rebuild / verify
    xet     XET textures (standard BC order, 0x2A YCbCr), block graft
    msg     GSM + FIM tables, control grammar, FIM contract derive/check/apply
    font    TNF metrics, CSA maps, line width measurement
    markup  lossless human-editable text markup for GSM word runs
    psl     PSL layout nodes (read-only)
    table   one message table (GSM+FIM+font) edited as text, contract kept
    patch   declarative patchsets: build, verify, install, rollback
    catalog translation catalogs: export, import, lint
"""
__version__ = "0.1.0"
