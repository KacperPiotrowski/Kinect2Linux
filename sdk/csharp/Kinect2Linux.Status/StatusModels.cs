using System.Text.Json.Serialization;

namespace Kinect2Linux.Status;

/// <summary>Read-only snapshot from `./kinect2 status --json` (schema version 1).</summary>
public sealed class KinectStatusSnapshot
{
    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("timestamp")]
    public DateTimeOffset Timestamp { get; init; }

    [JsonPropertyName("device")]
    public KinectDeviceInfo Device { get; init; } = new();

    [JsonPropertyName("rgb")]
    public KinectRgbInfo Rgb { get; init; } = new();

    [JsonPropertyName("ir")]
    public KinectIrInfo Ir { get; init; } = new();

    [JsonPropertyName("audio")]
    public KinectAudioInfo Audio { get; init; } = new();

    [JsonPropertyName("usb_lock")]
    public KinectUsbLockInfo UsbLock { get; init; } = new();

    /// <summary>
    /// Current RGB streaming state if and only if the bridge runtime state is fresh.
    /// null means unknown / not freshly confirmed, NOT 'camera is off'.
    /// </summary>
    [JsonIgnore]
    public bool? CurrentRgbStreaming => Rgb.StateFresh ? Rgb.SensorStreaming : null;

    [JsonIgnore]
    public int? CurrentRgbClientCount => Rgb.StateFresh ? Rgb.StreamingClients : null;
}

public sealed class KinectDeviceInfo
{
    [JsonPropertyName("connected")]
    public bool Connected { get; init; }

    [JsonPropertyName("sensors")]
    public List<KinectPhysicalSensor> Sensors { get; init; } = [];
}

public sealed class KinectPhysicalSensor
{
    [JsonPropertyName("usb_device")]
    public string? UsbDevice { get; init; }

    [JsonPropertyName("serial")]
    public string? Serial { get; init; }

    [JsonPropertyName("bus")]
    public string? Bus { get; init; }

    [JsonPropertyName("address")]
    public string? Address { get; init; }
}

public sealed class KinectRgbInfo
{
    [JsonPropertyName("virtual_device")]
    public string? VirtualDevice { get; init; }

    [JsonPropertyName("present")]
    public bool Present { get; init; }

    [JsonPropertyName("service")]
    public string? Service { get; init; }

    [JsonPropertyName("bridge_pid")]
    public int? BridgePid { get; init; }

    [JsonPropertyName("sensor_streaming")]
    public bool? SensorStreaming { get; init; }

    [JsonPropertyName("streaming_clients")]
    public int? StreamingClients { get; init; }

    [JsonPropertyName("state_source")]
    public string? StateSource { get; init; }

    [JsonPropertyName("state_fresh")]
    public bool StateFresh { get; init; }

    [JsonPropertyName("state_age_ms")]
    public long? StateAgeMs { get; init; }

    [JsonPropertyName("state_updated_at")]
    public DateTimeOffset? StateUpdatedAt { get; init; }

    [JsonPropertyName("capture_stats")]
    public KinectCaptureStats? CaptureStats { get; init; }

    [JsonPropertyName("openers")]
    public List<KinectCameraOpener> Openers { get; init; } = [];
}

public sealed class KinectCameraOpener
{
    [JsonPropertyName("pid")]
    public int Pid { get; init; }

    [JsonPropertyName("process")]
    public string? Process { get; init; }

    [JsonPropertyName("role")]
    public string? Role { get; init; }
}

public sealed class KinectCaptureStats
{
    [JsonPropertyName("frames")]
    public long? Frames { get; init; }

    [JsonPropertyName("seq_gaps")]
    public long? SequenceGaps { get; init; }

    [JsonPropertyName("output_drops")]
    public long? OutputDrops { get; init; }
}

public sealed class KinectIrInfo
{
    [JsonPropertyName("virtual_device")]
    public string? VirtualDevice { get; init; }

    [JsonPropertyName("present")]
    public bool Present { get; init; }
}

public sealed class KinectAudioInfo
{
    [JsonPropertyName("default_source")]
    public KinectAudioSource DefaultSource { get; init; } = new();
}

public sealed class KinectAudioSource
{
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("channels")]
    public int? Channels { get; init; }

    [JsonPropertyName("is_kinect")]
    public bool? IsKinect { get; init; }
}

public sealed class KinectUsbLockInfo
{
    [JsonPropertyName("path")]
    public string? Path { get; init; }

    [JsonPropertyName("held")]
    public bool? Held { get; init; }

    [JsonPropertyName("owner_pid")]
    public int? OwnerPid { get; init; }

    [JsonPropertyName("owner_name")]
    public string? OwnerName { get; init; }
}
