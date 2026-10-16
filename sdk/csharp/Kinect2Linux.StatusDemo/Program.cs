using Kinect2Linux.Status;

// Launch from the repository root, or pass it as the first argument.
var root = args.Length > 0 ? args[0] : Directory.GetCurrentDirectory();
try
{
    var client = new KinectStatusClient(root);
    var state = await client.ReadAsync();

    Console.WriteLine($"USB: {(state.Device.Connected ? "podłączony" : "brak")}");
    Console.WriteLine($"RGB: {state.Rgb.VirtualDevice} | usługa={state.Rgb.Service}");

    // A stale journal result must never be presented as live sensor state.
    var rgbState = state.CurrentRgbStreaming switch
    {
        true => "aktywny",
        false => "uśpiony",
        null => "nieznany (brak świeżego odczytu)"
    };
    Console.WriteLine($"Stan RGB: {rgbState}");
    Console.WriteLine($"Odbiorcy: {state.CurrentRgbClientCount?.ToString() ?? "nieznani"}");
    Console.WriteLine($"Klatki: {state.Rgb.CaptureStats?.Frames?.ToString() ?? "brak danych"}");
    Console.WriteLine($"Luki: {state.Rgb.CaptureStats?.SequenceGaps?.ToString() ?? "brak danych"}");
    Console.WriteLine($"USB lock: {state.UsbLock.Held?.ToString() ?? "?"} ");
    Console.WriteLine($"Domyślny mikrofon: {state.Audio.DefaultSource.Description ?? "nieznany"}");

    // These processes merely opened /dev/video11; they are NOT proven to be viewers.
    foreach (var opener in state.Rgb.Openers)
        Console.WriteLine($"Otwarty V4L2: PID {opener.Pid}, {opener.Process} [{opener.Role}]");
}
catch (Exception error) when (error is IOException or UnauthorizedAccessException
                                   or TimeoutException or FormatException
                                   or NotSupportedException or InvalidOperationException)
{
    Console.Error.WriteLine($"Status Kinecta: {error.Message}");
    Environment.ExitCode = 1;
}
