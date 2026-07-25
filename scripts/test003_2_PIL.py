
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