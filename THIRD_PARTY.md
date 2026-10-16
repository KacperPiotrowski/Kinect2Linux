# Kod stron trzecich

`src/kinect_ir_bridge.cpp` został opracowany jako przykład integracji z publicznym API `libfreenect2` i był używany w naszych testach.
Kinect2-Linux łączy się dynamicznie z `libfreenect2` (OpenKinect, licencjonowanie Apache-2.0/GPL-2.0; patrz oryginalne repozytorium).
Nie zawiera kodu źródłowego Microsoft Kinect SDK 2.0.
`howdy` jest wywoływany jako osobny program; nie kopiujemy jego modułów.
Dodatkowe zależności: OpenCV, dlib (opcjonalne), v4l2loopback.

Przed publiczną dystrybucją pakietów należy przejrzeć zakres i zgodność licencji
wszystkich komponentów oraz pochodzenie wkładów.
