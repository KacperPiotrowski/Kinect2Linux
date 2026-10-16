# Zasady bezpieczeństwa (Security Policy)

Kinect2-Linux jest projektem eksperymentalnym. Nie udostępniamy jeszcze stabilnego wydania SDK ani gwarantowanego okresu wsparcia bezpieczeństwa.

## Obsługiwane wersje

Poprawki bezpieczeństwa rozpatrujemy obecnie w aktywnie rozwijanej gałęzi `main`. Starsze commity, prototypy i kopie eksperymentalne nie są osobno utrzymywane. Nie deklarujemy czasu reakcji ani terminu wydania poprawki.

## Poufne zgłaszanie podatności

Jeżeli znalazłeś podatność w kodzie, skryptach instalacyjnych, obsłudze uprawnień, IPC lub zależnościach Kinect2-Linux:

1. Otwórz zakładkę [Security](https://github.com/KacperPiotrowski/Kinect2Linux/security) i użyj opcji **Report a vulnerability**, jeśli prywatne zgłaszanie jest włączone.
2. Nie publikuj szczegółów exploita, sekretów ani danych użytkowników w publicznym Issue lub Pull Requeście.
3. Jeżeli nie ma opcji prywatnego zgłoszenia, utwórz publiczne zgłoszenie **bez technicznych szczegółów podatności**, prosząc maintenera o uruchomienie prywatnego kanału.

W zgłoszeniu podaj wersję lub SHA commita, dystrybucję i wersję Linuksa, opis wpływu, niezbędne kroki odtworzenia oraz propozycję poprawki (jeśli ją masz). Nie dołączaj autentycznych kluczy, nagrań mikrofonu, zdjęć osób ani innych danych biometrycznych. W miarę możliwości korzystaj z danych syntetycznych.

Prosimy o rozsądne ujawnianie informacji: najpierw zgłoszenie prywatne, a dopiero po uzgodnieniu zakresu i terminu — opis publiczny.

## Zakres i ograniczenia

Kinect2-Linux obsługuje sprzęt i lokalne usługi, ale **nie jest obecnie rozwiązaniem do bezpiecznej autoryzacji biometrycznej**. Części eksperymentalne (m.in. Face/Body Tracking) nie są osobno wspieranymi komponentami bezpieczeństwa.

Informacje o zależnościach, modelach i pochodzeniu plików zawiera [THIRD_PARTY.md](THIRD_PARTY.md).
