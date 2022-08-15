import XMonad

import XMonad.Util.EZConfig
import XMonad.Util.Ungrab
import XMonad.Util.NamedScratchpad;

import XMonad.Layout.ThreeColumns
import XMonad.Layout.Magnifier

import XMonad.Hooks.EwmhDesktops
import XMonad.Hooks.ManageDocks
import XMonad.Hooks.ManageHelpers


import XMonad.Hooks.DynamicLog
import XMonad.Hooks.StatusBar
import XMonad.Hooks.StatusBar.PP

import XMonad.Actions.DynamicProjects
import XMonad.Prompt
import XMonad.Hooks.DynamicProperty (dynamicPropertyChange, dynamicTitle)
import qualified XMonad.StackSet as W

homeManagerProgram :: String -> String
homeManagerProgram bin = "/etc/profiles/per-user/jack/bin/" ++ bin

browserBin = "google-chrome-stable"
terminalBin = homeManagerProgram "alacritty"
rofiBin = homeManagerProgram "rofi -show-icons -modi drun,ssh,window "

myFont = "iosevka"
base03  = "#002b36"
base02  = "#073642"
base01  = "#586e75"
base00  = "#657b83"
base0   = "#839496"
base1   = "#93a1a1"
base2   = "#eee8d5"
base3   = "#fdf6e3"
yellow  = "#b58900"
orange  = "#cb4b16"
red     = "#dc322f"
magenta = "#d33682"
violet  = "#6c71c4"
blue    = "#268bd2"
cyan    = "#2aa198"
green       = "#859900"

active = "#4EB4FA"


myPromptTheme :: XPConfig
myPromptTheme = def
    { font                  = myFont
    , bgColor               = base03
    , fgColor               = active
    , fgHLight              = base03
    , bgHLight              = active
    , borderColor           = base03
    , promptBorderWidth     = 0
    , height                = 25
    , position              = Top
    }

warmPromptTheme = myPromptTheme
    { bgColor               = yellow
    , fgColor               = base03
    , position              = Top
    }

projects :: [Project]
projects = 
  [ Project { projectName = "scratch"
            , projectDirectory = "~/"
            , projectStartHook = Just $ do spawn terminalBin 
            }
  , Project { projectName = "core"
            , projectDirectory = "~/Code/github.com/pairtreefamily/core-api/"
            , projectStartHook = Just $ do spawn (terminalBin ++ " --command poetry run python manage.py runserver")
            }
  ]

isSpotify = title =? "Spotify"

scratchpads :: NamedScratchpads
scratchpads = 
  [ NS "music" "spotify" isSpotify doFloat
  ]

myLayout = tiled ||| Mirror tiled ||| Full ||| threeCol
  where
    tiled = Tall nmaster delta ratio
    threeCol = magnifier $ ThreeColMid nmaster delta ratio
    nmaster = 1
    ratio = 1/2
    delta = 3/100

main :: IO ()
main = xmonad $ dynamicProjects projects $ ewmhFullscreen $ ewmh $ xmobarProp myConfig 

myManageHook :: ManageHook
myManageHook = composeAll
  [ className =? "Gimp" --> doFloat
  , isDialog --> doFloat
  , namedScratchpadManageHook scratchpads
  ]

myDynamicManageHook :: ManageHook
myDynamicManageHook =
  isSpotify --> forceCenterFloat

myConfig = def
  { modMask = mod4Mask -- mod4 is super key
  , layoutHook = myLayout
  , terminal = terminalBin
  , manageHook =   myManageHook
  , handleEventHook = dynamicTitle myDynamicManageHook
  }
  `additionalKeysP`
  [ ("M-x", spawn "betterlockscreen  --dim 10 -l") -- lock screen
  , ("M-d", spawn (rofiBin ++ "-show drun")) -- dmenu
  , ("M-e", spawn (rofiBin ++ "-show emoji")) -- rofi emojis
  , ("M-S-f", spawn (rofiBin ++ "-show window")) -- window switcher
  , ("M-s", unGrab *> spawn "snip")
  , ("M-p", unGrab *> spawn "pick")
  , ("M-m", namedScratchpadAction scratchpads "music")
  , ("M-w", spawn browserBin)
  , ("<F5>", spawn "/run/current-system/sw/bin/light -U 5")
  , ("S-<F5>", spawn "/run/current-system/sw/bin/light -U 1")
  , ("<F6>", spawn "/run/current-system/sw/bin/light -A 5")
  , ("S-<F6>", spawn "/run/current-system/sw/bin/light -A 1")
  , ("M-\\", switchProjectPrompt myPromptTheme)  
  ]


forceCenterFloat :: ManageHook
forceCenterFloat = doFloatDep move
  where
    move :: W.RationalRect -> W.RationalRect
    move _ = W.RationalRect x y w h

    w, h, x, y :: Rational
    w = 1/3
    h = 1/2
    x = (1-w)/2
    y = (1-h)/2

