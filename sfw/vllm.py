# Rudimentary VLLM support for generating descriptions of images.
#

from pathlib import Path
from PIL import Image
import io
import array
import ctypes
from llama_cpp import (Llama, clip_model_load,  llava_image_embed_make_with_bytes,
    llava_image_embed_p, llava_image_embed_free,  llava_eval_image_embed)

class VLLM:
    def prompt(self, prompt: str, image: Image.Image | Path | None = None) -> str:
        pass

    def heartbeat(self) -> bool:
        pass

class LLAVA(VLLM):
    """
    LLAMA CPP Based LLAVA implementation
    """
    MAX_TARGET_LEN = 256
    N_CTX = 2048
    def __init__(self, model: Path, mmproj: Path, temp: float = 0.1):
        self.temp = temp
        self.model_path = model
        self.mmproj_path = mmproj
        self.initialize_llm()

    def initialize_llm(self):
        self.llm = Llama(model_path=str(self.model_path), n_ctx=self.N_CTX, n_gpu_layers=1)
        self.ctx_clip = clip_model_load(str(self.mmproj_path).encode('utf-8'))
        self.system_prompt()

    def load_image_path_embded(self, image: Path) -> llava_image_embed_p:
        with open(image, 'rb') as file:
            image_bytes = file.read()
            bytes_length = len(image_bytes)
            data_array = array.array('B', image_bytes)
            c_ubyte_ptr = (ctypes.c_ubyte * len(data_array)).from_buffer(data_array)
        return llava_image_embed_make_with_bytes(ctx_clip=self.ctx_clip, n_threads=1, image_bytes=c_ubyte_ptr, image_bytes_length=bytes_length)

    def load_image_embed(self, image: Image.Image) -> llava_image_embed_p:
        output = io.BytesIO()
        image.save(output, format='JPEG')
        return llava_image_embed_make_with_bytes(ctx_clip=self.ctx_clip, n_threads=1, image_bytes=output.getvalue(), image_bytes_length=output.tell())


    def eval_img(self, image: Image.Image | Path):
        if isinstance(image, Image.Image):
            im = self.load_image_embed(image)
        else:
            im = self.load_image_path_embded(image)
        n_past = ctypes.c_int(self.llm.n_tokens)
        n_past_p = ctypes.byref(n_past)
        llava_eval_image_embed(self.llm.ctx, im, self.llm.n_batch, n_past_p)
        self.llm.n_tokens = n_past.value
        llava_image_embed_free(im)

    def output(self, stream = True):
        res = ""
        for i in range(self.MAX_TARGET_LEN):
            t_id = self.llm.sample(temp=self.temp)
            t = self.llm.detokenize([t_id]).decode('utf8')
            if t == "</s>":
                break
            if stream:
                print(t, end="")
            res += t
            self.llm.eval([t_id])
        return res

    def system_prompt(self):
        self.llm.eval(self.llm.tokenize(b"You are a helpful assistant that objectively describes images."))

    def prompt(self, prompt: str, image: Image.Image | Path | None = None, refresh: bool=False, stream: bool=False) -> str:
        if refresh:
            self.initialize_llm()
        self.llm.eval(self.llm.tokenize("\nUSER: ".encode('utf8')))
        if image is not None:
            self.eval_img(image)
        self.llm.eval(self.llm.tokenize(prompt.encode("utf8")))
        self.llm.eval(self.llm.tokenize("\nASSISTANT:".encode("utf8")))
        return self.output()

    def heartbeat(self) -> bool:
        return self.llm is not None