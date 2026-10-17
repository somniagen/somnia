import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from somnia import gallery, models

LOCAL = [
    {"id": "checkpoint:waiIllustriousSDXL_v170.safetensors", "kind": "checkpoint", "family": "illustrious", "name": "waiIllustriousSDXL_v170"},
    {"id": "checkpoint:animayume_v15.safetensors", "kind": "checkpoint", "family": "anima", "name": "animayume_v15"},
    {"id": "lora:style/detailer_v2.safetensors", "kind": "lora", "family": "illustrious", "name": "detailer_v2"},
]
models.list_models = lambda kind=None: [m for m in LOCAL if kind is None or m["kind"] == kind]


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


def png(**chunks) -> Image.Image:
    info = PngInfo()
    for k, v in chunks.items():
        info.add_text(k, v if isinstance(v, str) else json.dumps(v))
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "PNG", pnginfo=info)
    buf.seek(0)
    return Image.open(buf)


a1111 = (
    "1girl, solo, <lora:detailer_v2:0.8>, <lora:missing:1>, smile\n"
    "Negative prompt: lowres, bad hands\n"
    "Steps: 30, Sampler: DPM++ 2M, Schedule type: Karras, CFG scale: 6.5, Seed: 1234, Size: 832x1216, "
    'Model hash: abc, Model: waiIllustriousSDXL_v170, Lora hashes: "detailer_v2: 123", Clip skip: 2, '
    "Hires upscale: 1.5, Hires steps: 12, Denoising strength: 0.4"
)
p = gallery.read_params(png(parameters=a1111))
check(p["sampler"] == "dpmpp_2m" and p["scheduler"] == "karras", "a1111 sampler + schedule type")
check(p["model"] == "checkpoint:waiIllustriousSDXL_v170.safetensors", "a1111 model mapped to local id")
check(p["loras"] == [{"id": "lora:style/detailer_v2.safetensors", "weight": 0.8}], "a1111 local lora moved into loras")
check("<lora:missing:1>" in p["prompt"] and "detailer_v2" not in p["prompt"], "unknown lora tag kept in prompt")
check((p["width"], p["height"], p["seed"], p["steps"], p["cfg"], p["clipSkip"]) == (832, 1216, 1234, 30, 6.5, 2), "a1111 numbers")
check(p["negative"] == "lowres, bad hands", "a1111 negative")
check(p["secondPass"]["enabled"] and p["secondPass"]["scale"] == 1.5 and p["secondPass"]["steps"] == 12, "a1111 hires as second pass")
p = gallery.read_params(png(parameters="a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 5, Size: 512x512"))
check(p["sampler"] == "euler_a", "a1111 plain euler a")
p = gallery.read_params(png(parameters="x\nSteps: 20, Sampler: DPM++ 2M SDE Karras, Seed: 5"))
check(p["sampler"] == "dpmpp_2m_sde" and p["scheduler"] == "karras", "old style sampler with folded scheduler")

prompt = {
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "SDXL\\waiIllustriousSDXL_v170.safetensors"}},
    "10": {"class_type": "LoraLoader", "inputs": {"lora_name": "detailer_v2.safetensors", "strength_model": 0.7, "strength_clip": 1, "model": ["4", 0], "clip": ["4", 1]}},
    "11": {"class_type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -2, "clip": ["10", 1]}},
    "20": {"class_type": "PrimitiveNode", "inputs": {"value": "masterpiece, 1girl"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ["20", 0], "clip": ["11", 0]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "worst quality", "clip": ["11", 0]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 896, "height": 1152, "batch_size": 1}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 28, "cfg": 5.5, "sampler_name": "euler_ancestral", "scheduler": "sgm_uniform",
                                                 "denoise": 1, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "12": {"class_type": "LatentUpscaleBy", "inputs": {"upscale_method": "bislerp", "scale_by": 1.25, "samples": ["3", 0]}},
    "13": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 14, "cfg": 5.5, "sampler_name": "euler", "scheduler": "normal",
                                                  "denoise": 0.45, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["12", 0]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["4", 2]}},
}
p = gallery.read_params(png(prompt=prompt))
check(p["prompt"] == "masterpiece, 1girl" and p["negative"] == "worst quality", "comfy prompts through links and primitives")
check(p["model"] == "checkpoint:waiIllustriousSDXL_v170.safetensors", "comfy checkpoint mapped")
check(p["loras"] == [{"id": "lora:style/detailer_v2.safetensors", "weight": 0.7}], "comfy lora loader")
check((p["seed"], p["steps"], p["cfg"], p["sampler"], p["scheduler"]) == (42, 28, 5.5, "euler_a", "sgm_uniform"), "comfy sampler fields from first pass")
check((p["width"], p["height"], p["clipSkip"]) == (896, 1152, 2), "comfy size and clip skip")
check(p["secondPass"]["enabled"] and p["secondPass"]["scale"] == 1.25 and p["secondPass"]["denoise"] == 0.45, "comfy second sampler as second pass")

unet = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "animayume_v15.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a fox"}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024}},
    "5": {"class_type": "KSamplerAdvanced", "inputs": {"noise_seed": 7, "steps": 30, "cfg": 4, "sampler_name": "er_sde", "scheduler": "simple",
                                                         "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
}
p = gallery.read_params(png(prompt=unet))
check(p["family"] == "anima" and p["model"] == "checkpoint:animayume_v15.safetensors", "comfy unet loader picks anima family")
check(p["seed"] == 7 and p["sampler"] == "er_sde" and p["prompt"] == "a fox", "comfy ksampler advanced")

workflow = {
    "nodes": [
        {"id": 4, "type": "CheckpointLoaderSimple", "widgets_values": ["waiIllustriousSDXL_v170.safetensors"], "inputs": []},
        {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["1boy"], "inputs": [{"name": "clip", "link": 3}]},
        {"id": 7, "type": "CLIPTextEncode", "widgets_values": ["bad"], "inputs": [{"name": "clip", "link": 5}]},
        {"id": 5, "type": "EmptyLatentImage", "widgets_values": [1024, 768, 1], "inputs": []},
        {"id": 3, "type": "KSampler", "widgets_values": [99, "fixed", 25, 6, "dpmpp_2m", "karras", 1],
         "inputs": [{"name": "model", "link": 1}, {"name": "positive", "link": 4}, {"name": "negative", "link": 6}, {"name": "latent_image", "link": 2}]},
    ],
    "links": [[1, 4, 0, 3, 0, "MODEL"], [2, 5, 0, 3, 3, "LATENT"], [3, 4, 1, 6, 0, "CLIP"], [4, 6, 0, 3, 1, "CONDITIONING"],
              [5, 4, 1, 7, 0, "CLIP"], [6, 7, 0, 3, 2, "CONDITIONING"]],
}
p = gallery.read_params(png(workflow=workflow))
check(p["prompt"] == "1boy" and p["negative"] == "bad" and p["seed"] == 99 and p["steps"] == 25, "comfy ui workflow only")
check((p["width"], p["height"], p["sampler"], p["scheduler"]) == (1024, 768, "dpmpp_2m", "karras"), "comfy workflow size and sampler")
check(gallery.read_params(png(prompt={"1": {"class_type": "Foo", "inputs": {}}})) is None, "graph without sampler gives nothing")
print("ALL PASSED")
