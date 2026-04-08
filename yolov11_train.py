import warnings
warnings.filterwarnings('ignore')
from ultralytics import YOLO
if __name__ == '__main__':
	model = YOLO('ultralytics/cfg/models/11/yolo11.yaml')   # 修改yaml
	model.load('yolo11n.pt')  #加载预训练权重
	# model.train(data='mydata.yaml',   #数据集yaml文件
	#             imgsz=640,
	#             epochs=80,
	#             batch=8,
	#             workers=6,  
	#             device=0,   #没显卡则将0修改为'cpu'
	#             optimizer='SGD',
    #             single_cls=False,  # 多类别设置False
    #             amp = False,
	#             cache=False,   #服务器可设置为True，训练速度变快
	# )
	model.train(
    data='mydata.yaml',
    imgsz=640,
    epochs=150,
    batch=8,
    device=0,

    optimizer='AdamW',
    amp=True,
    cache=False,

    close_mosaic=10,
    copy_paste=0.3,

    hsv_h=0.01,
    hsv_s=0.5,
    hsv_v=0.3,
    degrees=5,
    scale=0.3,
    shear=2,

    box=8.0,
    cls=0.5,
    dfl=1.5,
)