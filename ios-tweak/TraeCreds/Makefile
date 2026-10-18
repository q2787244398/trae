TARGET := iphone:clang:latest:15.0
ARCHS = arm64 arm64e
INSTALL_TARGET_PROCESSES = TRAE

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = TraeCreds
TraeCreds_FILES = Tweak.xm
TraeCreds_CFLAGS = -fobjc-arc
TraeCreds_FRAMEWORKS = UIKit Foundation Security

include $(THEOS_MAKE_PATH)/tweak.mk
