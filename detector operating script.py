import os
import time
import numpy as np
import RPi.GPIO as GPIO
from picamera2 import Picamera2, Preview

# LED setting
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(18, GPIO.OUT)  


# image capture 
def capture_image(filename, save_path, exposure_time=0.001):
    import cv2 
    os.makedirs(save_path, exist_ok=True)
    image_path = os.path.join(save_path, filename + ".jpg")
    camera = None
    
    try:
        GPIO.output(18, GPIO.HIGH)
        camera = Picamera2()
        camera_config = camera.create_still_configuration(
            main={"size": (1920, 1080)},
            lores={"size": (640, 480)},
            display="lores"
        )
        camera.configure(camera_config)
        try:
            camera.start_preview(Preview.QTGL)
        except Exception:
            pass

        camera.start()
        time.sleep(exposure_time)
        camera.capture_file(image_path)
        GPIO.output(18, GPIO.LOW)
        camera.stop()
        camera.close()

    except Exception as e:
        GPIO.output(18, GPIO.LOW)
        try:
            if camera:
                camera.stop()
                camera.close()
        except Exception:
            pass
        print(f"Failed to capture image: {e}")
        return False

   
    if not os.path.exists(image_path):
        print("Capture reported success but file not found.")
        return False
    print(f"Image saved: {image_path}")
    return image_path


# pixel sum computation 
def compute_pixel_sum(image_path): 
    import cv2
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Unable to read image: {image_path}")
    return int(np.sum(img, dtype=np.uint64))


# === CSV file creation ===
def _ensure_cumulative_csv(csv_path):
    import csv
    header = ["sample", "frame_index", "frame_basename", "frame_sum", "avg_sum", "std_sum"]
    need_header = (not os.path.exists(csv_path)) or (os.path.getsize(csv_path) == 0)
    if need_header:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)


def append_sample_to_cumulative_csv(save_path, sample_name, frame_basenames, frame_sums):
    import csv
    csv_path = os.path.join(save_path, "all_samples_sums.csv")
    _ensure_cumulative_csv(csv_path)

    avg_sum = float(np.mean(frame_sums))
    std_sum = float(np.std(frame_sums, ddof=1)) if len(frame_sums) > 1 else 0.0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for idx, (basename, s) in enumerate(zip(frame_basenames, frame_sums), start=1):
            writer.writerow([sample_name, idx, basename, int(s), "", ""])
        writer.writerow([sample_name, "summary", "", "", f"{avg_sum:.2f}", f"{std_sum:.2f}"])

    print(f"Appended to cumulative CSV: {csv_path}")
    return csv_path


if __name__ == "__main__":
    try:
        print("A typical path on Raspberry Pi is: /home/pi/<folder_name>")
        save_path = input("Please enter the path to save images and the cumulative CSV: ").strip()

        if not os.path.exists(save_path):
            print(f"The specified path does not exist. Creating directory: {save_path}")
            os.makedirs(save_path, exist_ok=True)

        #  User-defined parameters 
        expo_input = input("Exposure time (pre-capture sleep) (default 1 ms): ").strip()
        try:
            exposure_ms = float(expo_input) if expo_input else 1.0
        except ValueError:
            print("Invalid exposure; defaulting to 1 ms.")
            exposure_ms = 1.0
        exposure_s = max(0.0001, exposure_ms / 1000.0)

        delay_input = input("Delay between frames (default 5s): ").strip()
        try:
            delay_secs = float(delay_input) if delay_input else 5.0
        except ValueError:
            print("Invalid delay; defaulting to 5 seconds.")
            delay_secs = 5.0

        frames_input = input("Number of frames to capture per sample (default 3): ").strip()
        try:
            frames_per_sample = int(frames_input) if frames_input else 3
        except ValueError:
            print("Invalid number; defaulting to 3 frames per sample.")
            frames_per_sample = 3
        frames_per_sample = max(1, frames_per_sample)

        print("\nConfigured:")
        print(f"- Exposure sleep: {exposure_ms:.3f} ms")
        print(f"- Delay between frames: {delay_secs:.3f} s")
        print(f"- Frames per sample: {frames_per_sample}\n")
        print("      All results go to one CSV: all_samples_sums.csv\n")

        _ensure_cumulative_csv(os.path.join(save_path, "all_samples_sums.csv"))

        while True:
            sample_name = input("Enter sample name (without extension), or type 'q' to quit: ").strip()
            if sample_name.lower() == 'q':
                print("Exiting the program.")
                break

            frame_sums = []
            frame_basenames = []

            print(f"Starting sample '{sample_name}'")
            for i in range(1, frames_per_sample + 1):
                if i > 1:
                    print(f"Waiting {delay_secs:.3f} seconds before next frame...")
                    time.sleep(delay_secs)

                frame_basename = f"{sample_name}_{i:03d}"
                img_path = capture_image(frame_basename, save_path, exposure_time=exposure_s)
                if not img_path:
                    print("Skipping this frame due to capture failure.")
                    continue

                try:
                    s = compute_pixel_sum(img_path)
                except Exception as e:
                    print(f"Failed to compute pixel sum for {img_path}: {e}")
                    continue

                frame_basenames.append(frame_basename)
                frame_sums.append(s)
                print(f"Frame {frame_basename} sum: {s}")

            if not frame_sums:
                print(f"No valid frames captured for sample '{sample_name}'.")
                continue

            csv_path = append_sample_to_cumulative_csv(save_path, sample_name, frame_basenames, frame_sums)

            # Console summary
            avg_sum_console = float(np.mean(frame_sums))
            std_sum_console = float(np.std(frame_sums, ddof=1)) if len(frame_sums) > 1 else 0.0
            print("\n--- Sample Summary ---")
            print(f"Sample:                  {sample_name}")
            print(f"Frames captured:         {len(frame_sums)}")
            print(f"Average sum:             {avg_sum_console:.2f}")
            print(f"Std. deviation:          {std_sum_console:.2f}")
            print(f"Cumulative CSV at:       {csv_path}")
            print("-----------------------\n")

    finally:
        GPIO.output(18, GPIO.LOW)
        GPIO.cleanup()