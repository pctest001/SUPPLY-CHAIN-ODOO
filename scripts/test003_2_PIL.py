# 学习：类定义、init、实例方法、类方法
# 学习：继承、方法重写
# 学习：属性访问（@property）
# 学习：特殊方法（str, repr）
# 练习4：定义 OdooModel 基类和 StockQuant 子类
# 学习：HTTP 协议基础（GET/POST/状态码/Header/Body）
# 学习：requests 库（get, post, headers, params, json, timeout）
# 学习：响应处理（status_code, json(), text）
# 学习：会话管理（Session）
# 实战：用 requests 调用 httpbin.org/get
# 实战：用 requests 调用 httpbin.org/post 发送 JSON body
# 实战：处理超时和异常
# ✅ Checkpoint：能定义类和继承
# ✅ Checkpoint：能用 requests 发送 HTTP 请求并处理响应

from turtle import width

from PIL import Image,ImageFilter,ImageDraw, ImageFont

import random
#img = Image.open(r"E:\素材库\00001-287514416.png")  # 换成你实际的图片文件名
#img = Image.open("E:/素材库/00001-287514416.png")
img = Image.open("E:\\素材库\\00001-287514416.png")
print("尺寸:", img.size, "格式:", img.format)
img.show()
w, h = img.size
print('Original image size: %sx%s' % (w, h))
# 缩放到50%:
img.thumbnail((w//2, h//2))
print('Resize image to: %sx%s' % (w//2, h//2))
# 把缩放后的图像用jpeg格式保存:
img.save('thumbnail.jpg', 'jpeg')
# 应用模糊滤镜:
im2 = img.filter(ImageFilter.BLUR)
im2.save('blur.jpg', 'jpeg')

def rndChar():
    return chr(random.randint(65, 90))  
def rndColor():
    return (random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))
def rndColor2():
    return (random.randint(32, 127), random.randint(32, 127), random.randint(32, 127))      
width = 60 * 4
height = 60
image = Image.new('RGB', (width, height), (255, 255, 255))
font = ImageFont.truetype('arial.ttf', 36)
draw = ImageDraw.Draw(image)
for x in range(width):
    for y in range(height):
        draw.point((x, y), fill=rndColor())
for t in range(4):
    draw.text((60 * t + 10, 10), rndChar(), font=font, fill=rndColor2())
image = image.filter(ImageFilter.BLUR)
image.save('code.jpg', 'jpeg')