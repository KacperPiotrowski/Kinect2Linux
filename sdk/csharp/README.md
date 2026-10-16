# Kinect2-Linux — C# Status Client (read-only preview)

Niewielki przykład użycia istniejącego `./kinect2 status --json` w C#.
Nie zmienia plików Kinect2-Linux, nie otwiera USB, nie uruchamia Kinecta
oraz nie instaluje usługi. Zawiera bibliotekę z typowanymi modelami i demo.

## Wymagania

- Działający w katalogu projektu `./kinect2 status --json` (`schema_version: 1`)
- Linux oraz SDK **.NET 10** (LTS)
- Bez pakietów NuGet spoza .NET
- **Linux-only**: deklaracja `[assembly: SupportedOSPlatform("linux")]` jest generowana centralnie z `Directory.Build.props` dla wszystkich trzech projektów. Biblioteka dodatkowo sprawdza system przy utworzeniu klienta; nie wyciszamy reguły CA1416.
- `TargetFramework` pozostaje `net10.0` (bez wymuszania architektury `linux-x64`, dzięki czemu budowanie na innych architekturach Linuksa nie jest z góry blokowane).

Uruchom w głównym katalogu Kinect2-Linux:

```bash
dotnet run --project sdk/csharp/Kinect2Linux.Status.Tests
dotnet run --project sdk/csharp/Kinect2Linux.StatusDemo -- .
```

Przykład użycia biblioteki w własnym projekcie:

```csharp
using Kinect2Linux.Status;

var client = new KinectStatusClient("/ścieżka/do/Kinect2-Linux");
var s = await client.ReadAsync();
Console.WriteLine($"USB: {s.Device.Connected}");
Console.WriteLine($"RGB na żywo: {s.CurrentRgbStreaming?.ToString() ?? "nieznany"}");
```

Dodaj ProjectReference do `Kinect2Linux.Status.csproj`.

## Semantyka

- `Rgb.SensorStreaming` i `Rgb.StreamingClients` to **ostatnie znane** wartości.
- `CurrentRgbStreaming` i `CurrentRgbClientCount` są `null`, jeśli
  `Rgb.StateFresh == false`. `null` znaczy „nie wiemy”, nie „wyłączona”.
- `Rgb.Openers` to procesy z deskryptorami `/dev/video11`, **nie dowód**
  czytania klatek. Przy PipeWire/portalach tożsamość faktycznego odbiorcy
  może być niewidoczna.
- `Device.Connected` pochodzi z sysfs USB, `UsbLock.Held` z `/proc/locks`,
  a `Rgb.StateFresh` z pliku runtime mostka. To odrębne obserwacje.
- Jest to snapshot pobierany na żądanie, **nie** abonament zdarzeń i jeszcze
  **nie** C API ani pełne Kinect SDK 2.0.

## Bezpieczeństwo i publikacja

Kod używa `ProcessStartInfo.ArgumentList`, **bez powłoki/shell interpolation**.
Do GitHuba nie publikuj wygenerowanych plików `bin/`, `obj/`, nagrań twarzy,
prywatnych WAV, modeli biometrycznych ani lokalnych dumpów ze statusem
zawierających rzeczywisty numer seryjny sensora.

Przykładowe dane testowe są syntetyczne; nie zawierają numeru seryjnego
ani ścieżek domowych użytkownika. Kod można umieścić w istniejącym repozytorium.
