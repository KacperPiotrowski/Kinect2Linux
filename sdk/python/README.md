# Python SDK (w przygotowaniu)

To pierwszy krok pod przyszłe jedyne wysokopoziomowe SDK Kinect2-Linux.

Obecnie dostępny jest **wyłącznie kodek sterujących wiadomości IPC**: `kinect2_linux.ipc`. Nie ma jeszcze brokera C++, obsługi urządzenia z tego modułu, dostarczania klatek ani klasy `Kinect`. Nie używaj tego pakietu jako gotowego sterownika Kinecta.

Kontrakt: [docs/IPC-PROTOCOL.md](../../docs/IPC-PROTOCOL.md).

Testy offline uruchamia istniejący workflow repozytorium przez `python3 -m unittest discover -s tests -v`.
