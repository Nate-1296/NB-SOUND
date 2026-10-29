// Impide que se abra una consola además de la ventana en Windows en modo release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    nb_sound_lib::run();
}
