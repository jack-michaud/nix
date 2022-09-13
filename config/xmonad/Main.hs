import XMonad
import Data.List

import XMonad.Util.EZConfig
import XMonad.Util.Ungrab
import XMonad.Util.NamedScratchpad

import XMonad.Actions.UpdatePointer

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
import XMonad.Layout.Gaps (gaps)
import XMonad.Layout.Spacing (smartSpacingWithEdge)
import XMonad.Layout.NoBorders (noBorders)

homeManagerProgram :: String -> String
homeManagerProgram bin = "/etc/profiles/per-user/jack/bin/" ++ bin

browserBin = "google-chrome-stable"
terminalBin = "alacritty"
logseqBin = "logseq"
rofiBin = "rofi -show-icons -modi drun,ssh,window "
webcamBin = "mpv --untimed --no-cache --no-osc --no-input-default-bindings --profile=low-latency --input-conf=/dev/null --title=webcam /dev/video4"

myFont = "iosevka:14"
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

data ProjectContext = Work | Personal deriving Eq;

projects :: [Project]
projects = 
  [ Project { projectName = "scratch"
            , projectDirectory = "~/"
            , projectStartHook = Just $ do spawn terminalBin 
            }
  , Project { projectName = "support"
            , projectDirectory = "~/Code/github.com/pairtreefamily/core-api/"
            , projectStartHook = Just $ do spawn workBrowserBin
                                           spawn (terminalBin ++ " --command ssh script-host") 
            }
  , Project { projectName = "core"
            , projectDirectory = "~/Code/github.com/pairtreefamily/core-api/"
            , projectStartHook = Just $ do spawn (terminalBin ++ " --command poetry shell") 
                                           spawn (terminalBin ++ " --command poetry shell") 
                                           spawn (terminalBin ++ "docker-compose up")
            }
  ]

projectContext :: Project -> ProjectContext 
projectContext project =
  case projectName project of
    "scratch" -> Personal
    "core" -> Work
    "support" -> Work
    _ -> if isPrefixOf "work" (projectName project) then Work else Personal

workBrowserBin = browserBin ++ " --profile-directory=Work"
personalBrowserBin = browserBin ++ " --profile-directory=Personal"


isSpotify = className =? "Spotify"
isSlack = className =? "Slack"
isDiscord = className =? "discord"
isBluetoothDeviceManager = title =? "Bluetooth Devices"
isWorkCalendar = title ^? "PairTree - Calendar"
isClickup = className ^? "ClickUp"
isLogseq = className ^? "Logseq"
isWebcam = title =? "webcam"

workCalendarBin = workBrowserBin ++ " --app=https://calendar.google.com/"
clickupBin = "clickup"

scratchpads :: NamedScratchpads
scratchpads = 
  [ NS "music" "spotify" isSpotify doFloat
  , NS "work-comm" "slack" isSlack doFloat
  , NS "work-calendar" workCalendarBin isWorkCalendar doFloat
  , NS "personal-comm" "discord" isDiscord doFloat
  , NS "work-tasks" clickupBin isClickup doFloat
  , NS "dev-log" logseqBin isLogseq doFloat
  , NS "webcam" webcamBin isWebcam doFloat
  ]

myLayout = smartSpacingWithEdge 10 $ tiled ||| noBorders Full 
  where
    tiled = Tall nmaster delta ratio
    nmaster = 1
    ratio = 1/2
    delta = 3/100

currentProjectContext :: X ProjectContext
currentProjectContext = do projectContext <$> currentProject

isWorkContext :: X Bool
isWorkContext = do 
  context <- currentProjectContext
  return $ context == Work

isPersonalContext :: X Bool
isPersonalContext = do 
  context <- currentProjectContext
  return $ context == Personal

main :: IO ()
main = xmonad $ dynamicProjects projects $ ewmhFullscreen $ ewmh $ xmobarProp myConfig 

myManageHook :: ManageHook
myManageHook = composeAll
  [ className =? "Gimp" --> doFloat
  , isBluetoothDeviceManager --> doFloat
  , isDialog --> doFloat
  , namedScratchpadManageHook scratchpads
  ]

myDynamicManageHook :: ManageHook
myDynamicManageHook = composeAll
  [ isSpotify --> forceCenterFloat
  , isSlack --> doFloat
  , isDiscord --> doFloat
  , isWorkCalendar --> doFloat
  , isClickup --> doFloat
  , isLogseq --> doFloat
  ]

myConfig = def
  { modMask = mod4Mask -- mod4 is super key
  , layoutHook = myLayout
  , terminal = terminalBin
  , manageHook = myManageHook
  , focusedBorderColor = cyan
  , normalBorderColor = base03
  , logHook = updatePointer (0.01, 0.01) (0, 0) 
  , handleEventHook = dynamicPropertyChange "WM_CLASS" myDynamicManageHook
  }
  `additionalKeysP`
  [ ("M-x", spawn "betterlockscreen  --dim 10 -l") -- lock screen
  , ("M-d", spawn (rofiBin ++ "-show drun")) -- dmenu
  , ("M-e", spawn (rofiBin ++ "-show emoji")) -- rofi emojis
  , ("M-S-f", spawn (rofiBin ++ "-show window")) -- window switcher
  , ("M-s", unGrab *> spawn "snip")
  , ("M-c", whenX isWorkContext (namedScratchpadAction scratchpads "work-calendar"))
  , ("M-S-s", sequence_ [ whenX isWorkContext (namedScratchpadAction scratchpads "work-comm")
                        , whenX isPersonalContext (namedScratchpadAction scratchpads "personal-comm")
                        ])
  --, ("M-p", unGrab *> spawn "pick")
  , ("M-m", namedScratchpadAction scratchpads "music")
  , ("M-t", namedScratchpadAction scratchpads "work-tasks")
  , ("M-S-l", namedScratchpadAction scratchpads "dev-log")
  , ("M-S-w", namedScratchpadAction scratchpads "webcam")
  , ("M-w", sequence_ [ whenX isPersonalContext (spawn personalBrowserBin)
                      , whenX isWorkContext (spawn workBrowserBin)])
  , ("<F5>", spawn "/run/current-system/sw/bin/light -U 5")
  , ("S-<F5>", spawn "/run/current-system/sw/bin/light -U 1")
  , ("<F6>", spawn "/run/current-system/sw/bin/light -A 5")
  , ("S-<F6>", spawn "/run/current-system/sw/bin/light -A 1")
  , ("M-p", switchProjectPrompt myPromptTheme)  
  , ("M-S-p", shiftToProjectPrompt myPromptTheme)  
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

