using Kinect2Linux.Status;

if (!OperatingSystem.IsLinux())
    throw new PlatformNotSupportedException("Testy Kinect2Linux.Status sa przeznaczone na Linux.");

const string fixture = """
{
  "schema_version": 1,
  "timestamp": "2026-01-01T00:00:00+00:00",
  "device": {"connected": true, "sensors": [{"serial": null, "usb_device": "4-2", "bus": "4", "address": "2"}]},
  "rgb": {
    "virtual_device": "/dev/video11", "present": true, "service": "active",
    "bridge_pid": 1234, "sensor_streaming": true, "streaming_clients": 1,
    "state_source": "bridge_runtime", "state_fresh": true, "state_age_ms": 15,
    "capture_stats": {"frames": 538, "seq_gaps": 0, "output_drops": 0},
    "openers": [{"pid": 5678, "process": "example-app", "role": "opener_not_proven_streaming"}]
  },
  "ir": {"virtual_device": "/dev/video10", "present": true},
  "audio": {"default_source": {"description": "test device", "channels": 4, "is_kinect": true}},
  "usb_lock": {"held": true, "owner_pid": 1234, "owner_name": "bridge"}
}
""";

static void Assert(bool condition, string text)
{
    if (!condition) throw new Exception($"FAILED: {text}");
}

var live = KinectStatusClient.ParseJson(fixture);
Assert(live.SchemaVersion == 1, "schema");
Assert(live.CurrentRgbStreaming == true, "fresh ON");
Assert(live.CurrentRgbClientCount == 1, "fresh clients");
Assert(live.Rgb.CaptureStats?.Frames == 538, "frame stats");
Assert(live.Audio.DefaultSource.Channels == 4, "microphone channels");
Assert(live.Rgb.Openers[0].Role == "opener_not_proven_streaming", "open is not verified streaming");

var stale = KinectStatusClient.ParseJson(fixture.Replace("\"state_fresh\": true", "\"state_fresh\": false"));
Assert(stale.Rgb.SensorStreaming == true, "last known raw observation remains available");
Assert(stale.CurrentRgbStreaming is null, "stale must not be presented as live");
Assert(stale.CurrentRgbClientCount is null, "stale clients are unknown");

var unknown = KinectStatusClient.ParseJson(fixture.Replace("\"sensor_streaming\": true", "\"sensor_streaming\": null"));
Assert(unknown.CurrentRgbStreaming is null, "unknown must not be OFF");

var wrongSchemaRejected = false;
try { KinectStatusClient.ParseJson(fixture.Replace("\"schema_version\": 1", "\"schema_version\": 2")); }
catch (NotSupportedException) { wrongSchemaRejected = true; }
Assert(wrongSchemaRejected, "future schema rejection");

// End-to-end test of the read-only adapter with a synthetic launcher.
// It does not connect to the physical sensor or the user's systemd session.
var root = Path.Combine(Path.GetTempPath(), $"kinect2-status-test-{Guid.NewGuid():N}");
Directory.CreateDirectory(root);
try
{
    var launcher = Path.Combine(root, "kinect2");
    File.WriteAllText(launcher,
        "#!/bin/sh\n" +
        "[ \"$1\" = \"status\" ] && [ \"$2\" = \"--json\" ] || exit 3\n" +
        "cat <<'K2_JSON'\n" + fixture + "\nK2_JSON\n");
    File.SetUnixFileMode(launcher,
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
    var client = new KinectStatusClient(root);
    var fromProcess = await client.ReadAsync();
    Assert(fromProcess.CurrentRgbStreaming == true, "CLI process JSON read");
    Assert(fromProcess.Rgb.CaptureStats?.SequenceGaps == 0, "CLI process stats");
}
finally
{
    Directory.Delete(root, recursive: true);
}

Console.WriteLine("PASS: świeży status, stary status, brak danych, kanały, schemat JSON, uruchomienie CLI.");
