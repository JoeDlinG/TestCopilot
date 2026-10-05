from PIL import Image, ImageDraw

S = 256
img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(198, 40, 40, 255))
d.line(
    [(40, 150), (70, 150), (90, 90), (110, 180), (130, 110), (150, 160), (170, 130), (200, 130)],
    fill=(255, 255, 255, 255), width=12, joint='curve',
)
img.save(r'D:/TestCopilot/backend/static/aitestlab.ico',
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('icon written')
