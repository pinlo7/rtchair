"""常量定义。"""

DOMAIN = "rtchair"
DEFAULT_BASE_URL = "http://192.168.1.1:8891"
DEFAULT_NAME = "荣泰按摩椅"
SCAN_INTERVAL = 5

PROGRAMS = {
    16: "椅上瑜伽", 17: "脑力唤醒", 18: "放松冥想", 19: "总裁尊享", 20: "女王尊享",
    21: "乐龄尊享", 22: "颈肩舒缓", 23: "脊背呵护", 24: "腰臀运动", 25: "清晨活力",
    26: "午间小憩", 27: "良宵甜梦",
}
SKILLS = {1: "揉捏", 2: "敲击", 3: "揉敲", 4: "叩击", 5: "指压", 8: "深度指压"}
TIMES = {1: "10 分钟", 2: "20 分钟", 3: "30 分钟"}
POSITIONS = {1: "全程", 2: "局部", 3: "定点"}
CHAIR_STATUS = {0: "关机", 1: "工作/复位", 2: "待机", 3: "运行中"}

# 预设程序：(延迟秒, 属性字典)
PRESET_PLANS = {
    "久坐救星": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 3, "SettingMassageSkill": 1, "SettingStrength3D": 3,
             "SettingSpeedMotor": 2, "SettingMotorPosition": 1, "SettingHeatBack": 2,
             "SettingAllAirBag": 1, "SettingStrengthAirBag": 3}),
        (360, {"SettingMassageSkill": 5, "SettingMotorPosition": 2, "SettingStrength3D": 4}),
        (720, {"SettingMassageSkill": 2, "SettingSpeedMotor": 1, "SettingStrength3D": 4,
               "SettingStrengthAirBag": 4}),
        (1080, {"SettingMassageSkill": 3, "SettingMotorPosition": 1, "SettingSpeedMotor": 2,
                "SettingZeroGravity": 1}),
        (1440, {"SettingMassageSkill": 1, "SettingStrength3D": 2, "SettingHeatBack": 3,
                "SettingZeroGravity": 0}),
        (1500, {"SettingMassageTime": 3}),
    ],
    "肩颈重点": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 2, "SettingMassageSkill": 5, "SettingStrength3D": 4,
             "SettingSpeedMotor": 2, "SettingMotorPosition": 2, "SettingHeatBack": 3}),
        (300, {"SettingMassageSkill": 1, "SettingStrength3D": 3, "SettingMotorPosition": 1}),
        (540, {"SettingMassageSkill": 8, "SettingStrength3D": 4, "SettingSpeedMotor": 1,
               "SettingMotorPosition": 3}),
        (780, {"SettingMassageSkill": 3, "SettingStrength3D": 3, "SettingSpeedMotor": 2,
               "SettingMotorPosition": 2}),
        (1020, {"SettingMassageSkill": 2, "SettingStrength3D": 2, "SettingHeatBack": 1}),
    ],
    "快速回血": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 1, "SettingMassageSkill": 1, "SettingStrength3D": 4,
             "SettingSpeedMotor": 3, "SettingMotorPosition": 1, "SettingHeatBack": 3}),
        (150, {"SettingMassageSkill": 5, "SettingStrength3D": 3, "SettingSpeedMotor": 2}),
        (300, {"SettingMassageSkill": 4, "SettingStrength3D": 2}),
        (540, {"SettingMassageSkill": 1, "SettingStrength3D": 2, "SettingHeatBack": 1}),
    ],
    "腰部加强": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 2, "SettingMassageSkill": 3, "SettingStrength3D": 4,
             "SettingSpeedMotor": 2, "SettingMotorPosition": 2, "SettingHeatBack": 3,
             "SettingWaistAirBag": 1, "SettingStrengthAirBag": 3}),
        (300, {"SettingMassageSkill": 1, "SettingStrength3D": 4, "SettingMotorPosition": 1,
               "SettingAllAirBag": 1}),
        (600, {"SettingMassageSkill": 2, "SettingSpeedMotor": 1, "SettingStrength3D": 3}),
        (900, {"SettingMassageSkill": 5, "SettingStrength3D": 3, "SettingHeatBack": 2}),
        (1140, {"SettingMassageSkill": 1, "SettingStrength3D": 2}),
    ],
    "全身舒缓": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 3, "SettingMassageSkill": 1, "SettingStrength3D": 2,
             "SettingSpeedMotor": 2, "SettingMotorPosition": 1, "SettingHeatBack": 2,
             "SettingHeatShank": 1, "SettingZeroGravity": 1, "SettingAllAirBag": 1,
             "SettingStrengthAirBag": 2}),
        (600, {"SettingMassageSkill": 3, "SettingStrength3D": 2, "SettingSpeedMotor": 2}),
        (1200, {"SettingMassageSkill": 2, "SettingSpeedMotor": 1, "SettingStrength3D": 1}),
        (1620, {"SettingMassageSkill": 1, "SettingStrength3D": 1, "SettingHeatBack": 1}),
    ],
    "睡前安神": [
        (0, {"ChairSwitch": 1}),
        (4, {"SettingMassageTime": 2, "SettingMassageSkill": 1, "SettingStrength3D": 1,
             "SettingSpeedMotor": 1, "SettingMotorPosition": 1, "SettingZeroGravity": 1,
             "SettingHeatBack": 1, "SettingHeatShank": 1}),
        (360, {"SettingAllAirBag": 1, "SettingStrengthAirBag": 2}),
        (720, {"SettingMassageSkill": 3, "SettingStrength3D": 1, "SettingSpeedMotor": 1}),
        (960, {"SettingStrengthAirBag": 1, "SettingHeatShank": 2}),
    ],
}
