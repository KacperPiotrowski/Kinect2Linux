using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace Kinect2Linux.Status;

/// <summary>
/// Read-only adapter over Kinect2-Linux's stable CLI JSON contract.
/// Does not open the sensor, acquire the Kinect USB lock or start the RGB bridge.
/// Linux only: invokes the existing `kinect2` executable without a shell.
/// </summary>
public sealed class KinectStatusClient
{
    private static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(15);

    private readonly string _repoRoot;
    private readonly string _executable;

    public KinectStatusClient(string repositoryRoot)
    {
        if (!OperatingSystem.IsLinux())
            throw new PlatformNotSupportedException("Kinect2Linux.Status jest obecnie wspierany tylko na Linuksie.");

        ArgumentException.ThrowIfNullOrWhiteSpace(repositoryRoot);
        _repoRoot = Path.GetFullPath(repositoryRoot);
        _executable = Path.Combine(_repoRoot, "kinect2");
        if (!File.Exists(_executable))
            throw new FileNotFoundException("Nie znaleziono launchera Kinect2-Linux", _executable);
    }

    public async Task<KinectStatusSnapshot> ReadAsync(
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var duration = timeout ?? DefaultTimeout;
        if (duration <= TimeSpan.Zero)
            throw new ArgumentOutOfRangeException(nameof(timeout), "Timeout musi być dodatni.");

        using var process = new Process { StartInfo = CreateStatusProcessStartInfo() };
        using var timeoutToken = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutToken.CancelAfter(duration);

        cancellationToken.ThrowIfCancellationRequested();
        if (!process.Start())
            throw new IOException("Nie udało się uruchomić `kinect2 status --json`.");

        // Drain both pipes concurrently to avoid process deadlocks.
        var stdout = process.StandardOutput.ReadToEndAsync(timeoutToken.Token);
        var stderr = process.StandardError.ReadToEndAsync(timeoutToken.Token);
        try
        {
            await process.WaitForExitAsync(timeoutToken.Token).ConfigureAwait(false);
            var json = await stdout.ConfigureAwait(false);
            var errors = await stderr.ConfigureAwait(false);
            if (process.ExitCode != 0)
                throw new InvalidOperationException(
                    $"kinect2 status --json zakończył się kodem {process.ExitCode}: {errors.Trim()}");
            return ParseJson(json);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException($"Odczyt statusu Kinecta przekroczył {duration.TotalSeconds:0.#} s.");
        }
        finally
        {
            // Kill only our own CLI process, never the RGB bridge or Kinect service.
            if (!process.HasExited)
            {
                try { process.Kill(entireProcessTree: true); }
                catch (InvalidOperationException) { }
            }
        }
    }

    /// <summary>
    /// Build per-invocation process options. ProcessStartInfo is mutable, so sharing
    /// a single instance across concurrent ReadAsync calls would be unsafe.
    /// </summary>
    private ProcessStartInfo CreateStatusProcessStartInfo()
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = _executable,
            WorkingDirectory = _repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        startInfo.ArgumentList.Add("status");
        startInfo.ArgumentList.Add("--json");
        return startInfo;
    }

    /// <summary>Parse an offline snapshot or CLI output; rejects unknown schema versions.</summary>
    public static KinectStatusSnapshot ParseJson(string json)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(json);
        KinectStatusSnapshot result;
        try
        {
            result = JsonSerializer.Deserialize<KinectStatusSnapshot>(json)
                ?? throw new JsonException("Pusty JSON statusu.");
        }
        catch (JsonException error)
        {
            throw new FormatException("Niepoprawny JSON Kinect2-Linux Status API.", error);
        }
        if (result.SchemaVersion != 1)
            throw new NotSupportedException(
                $"Nieobsługiwana wersja schematu Status API: {result.SchemaVersion} (wymagana 1).");
        return result;
    }
}
