"""Генерация тестовых аудио-файлов для интеграционных тестов.

Создаёт WAV файлы с синтетическим речевым контентом:
- short_meeting.wav — короткое собрание (~10 сек)
- long_meeting.wav — длинное собрание (~30 сек)
- risk_meeting.wav — собрание с "опасным" контентом
- noise_meeting.wav — собрание с шумом
- single_speaker.wav — один говорящий
"""
import os
import struct
import wave

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "audio")


def generate_wav(filename: str, duration_sec: float, sample_rate: int = 16000,
                 frequency: int = 440, amplitude: int = 16000,
                 silence_segments: list = None):
    """Генерация WAV файла с заданными параметрами.
    
    Args:
        filename: имя выходного файла
        duration_sec: длительность в секундах
        sample_rate: частота дискретизации
        frequency: частота тона (Гц)
        amplitude: амплитуда (0-32767)
        silence_segments: список (start_sec, duration_sec) для тишины
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    
    num_samples = int(sample_rate * duration_sec)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        for i in range(num_samples):
            t = i / sample_rate
            
            # Проверка тишины
            is_silence = False
            if silence_segments:
                for s_start, s_dur in silence_segments:
                    if s_start <= t < s_start + s_dur:
                        is_silence = True
                        break
            
            if is_silence:
                sample = 0
            else:
                # Синтетическая речь — меняем частоту для имитации речи
                # Модулируем частоту с помощью низкой частоты
                mod_freq = frequency + 100 * (i % 100) / 100
                sample = int(amplitude * 0.5 * (
                    0.3 * (1 if (i % 200) < 100 else -1) +  # Основная частота
                    0.1 * (1 if (i % 50) < 25 else -1) +      # Обертон
                    0.05 * ((i * 7) % 200 - 100) / 100        # Шум
                ))
                sample = max(-32768, min(32767, sample))
            
            wf.writeframes(struct.pack("<h", sample))
    
    print(f"Generated: {path} ({duration_sec:.1f}s, {sample_rate}Hz)")
    return path


def generate_risk_wav(filename: str, duration_sec: float = 15):
    """Генерация WAV с "опасным" контентом (для тестирования risk detection)."""
    # Частоты, имитирующие разные "спикеры"
    segments = [
        (0, 3, 440, 16000),    # Спикер 1
        (3, 1, 0, 0),           # Пауза
        (4, 4, 380, 14000),     # Спикер 2
        (8, 1, 0, 0),           # Пауза
        (9, 3, 500, 15000),     # Спикер 3
        (12, 3, 0, 0),          # Пауза
    ]
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    sample_rate = 16000
    num_samples = int(sample_rate * duration_sec)
    
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        seg_idx = 0
        for i in range(num_samples):
            t = i / sample_rate
            
            freq = 440
            amp = 16000
            if seg_idx < len(segments):
                s_start, s_dur, s_freq, s_amp = segments[seg_idx]
                if s_start <= t < s_start + s_dur:
                    freq = s_freq
                    amp = s_amp
                elif t >= s_start + s_dur:
                    seg_idx += 1
                    if seg_idx < len(segments):
                        s_start, s_dur, s_freq, s_amp = segments[seg_idx]
                        if s_start <= t < s_start + s_dur:
                            freq = s_freq
                            amp = s_amp
            
            sample = int(amp * 0.5 * (
                0.3 * (1 if (i % 200) < 100 else -1) +
                0.1 * (1 if (i % 50) < 25 else -1) +
                0.05 * ((i * 7) % 200 - 100) / 100
            ))
            sample = max(-32768, min(32767, sample))
            wf.writeframes(struct.pack("<h", sample))
    
    print(f"Generated: {path} ({duration_sec:.1f}s, {sample_rate}Hz)")
    return path


if __name__ == "__main__":
    print("Generating test audio files...")
    
    # Короткое собрание (~10 сек)
    generate_wav("short_meeting.wav", duration_sec=10)
    
    # Длинное собрание (~30 сек)
    generate_wav("long_meeting.wav", duration_sec=30)
    
    # С собранием с "опасным" контентом
    generate_risk_wav("risk_meeting.wav", duration_sec=15)
    
    # С шумом (более высокая амплитуда шума)
    generate_wav("noise_meeting.wav", duration_sec=20, amplitude=20000)
    
    # Один говорящий (одинаковая частота)
    generate_wav("single_speaker.wav", duration_sec=15, frequency=440)
    
    print(f"\nAll files generated in {OUTPUT_DIR}/")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(path)
        print(f"  {f}: {size / 1024:.1f} KB")
