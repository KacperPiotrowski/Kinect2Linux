# C# SDK — porządki po review

Zmiany względem pierwszej paczki:

- `sdk/csharp/Directory.Build.props`: centralne ustawienia dla trzech projektów.
- `KinectStatusClient.DefaultTimeout`: `static readonly TimeSpan` (15 sekund).
- `CreateStatusProcessStartInfo()`: jedna metoda konfigurująca nowe `ProcessStartInfo` przy każdym wywołaniu. Obiekt jest mutowalny, a `ReadAsync` może być wywołana współbieżnie.
- `ConfigureAwait(false)` pozostaje wyłącznie w bibliotece jako świadoma decyzja dla konsumentów z własnym `SynchronizationContext`.

Zachowano publiczny kontrakt JSON, modele, timeout, anulowanie i testy z pierwszej wersji. Brak zmian w C++, Kinect USB, Qt, systemd i Pythonie.

Uruchom lokalnie z .NET 10:

```sh
dotnet run --project sdk/csharp/Kinect2Linux.Status.Tests
dotnet run --project sdk/csharp/Kinect2Linux.StatusDemo -- .
```

W tej sesji `dotnet` nie był dostępny, dlatego nie należy traktować paczki jako skompilowanej i przetestowanej uruchomieniowo.

## Linux-only i CA1416 (kolejna iteracja)

- `Directory.Build.props` dodaje dla wszystkich trzech projektów atrybut `[assembly: System.Runtime.Versioning.SupportedOSPlatform("linux")]` przez MSBuild `AssemblyAttribute`.
- `KinectStatusClient` odrzuca inne systemy przez `PlatformNotSupportedException`.
- Testy mają jawne sprawdzenie `OperatingSystem.IsLinux()` przed użyciem `File.SetUnixFileMode`.
- Zachowane: `net10.0`, `TreatWarningsAsErrors`, `ConfigureAwait(false)`, niezmienny fabryczny `ProcessStartInfo` dla każdego wywołania.
- Bez lokalnego SDK `dotnet` nie dało się potwierdzić kompilacji na tym środowisku.
