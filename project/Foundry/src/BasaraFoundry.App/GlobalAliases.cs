// WinUI imports Windows.Storage.Streams.Buffer in the app project. Foundry's
// pixel-copy helpers intentionally use the CLR block-copy implementation.
// Keep the simple Buffer name deterministic across partial MainWindow files.
global using Buffer = System.Buffer;
