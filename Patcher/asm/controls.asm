; Keyboard + mouse controls for INDARK.EXE (GOG), the DOS version of the ReHaunted option
; (TatouSource/FitdLib/modernControls.cpp). Design: Research/VanillaControls_Design.md;
; every address: Research/VanillaControls_Investigation.md (checked against the GOG bytes).
;
; Appended as a new segment (vanilla_exe.py --controls). The game enters it by far jumps
; written over eight instructions (the entry_* labels); each entry redoes the displaced
; instruction and jumps back. Far jumps/calls into the game are written as bytes with
; file-relative segments; the words labelled reloc_* get relocation entries (build_controls.py
; reads both label kinds from the listing). State lives in this segment (CS-relative), so the
; keyboard interrupt part never depends on DS. DS is the game's data segment (294c) at every
; entry.

        ; no CPU directive (ML 14 rejects .186/.286): the build rejects 386 encodings
CTRL    SEGMENT USE16 PUBLIC 'CODE'
        ASSUME  CS:CTRL, DS:NOTHING, ES:NOTHING

; ---- game data (DS = 294c) ----
RAW_JOYD    EQU 7CA0h       ; directions written by IRQ1 (byte used)
RAW_CLICK   EQU 7CAAh
MODIFIERS   EQU 7CB6h       ; IRQ1: Shift 2, Ctrl 4
TO_BIOS     EQU 7CA8h       ; nonzero while a save name is typed
LAYOUT      EQU 7CBEh       ; layout translation on (tested at the IRQ1 hook)
LOC_CLICK   EQU 8BAAh       ; PlayWorld's copies
LOC_JOYD    EQU 8BACh
LOC_KEY     EQU 8BAEh
ANTIREBOND  EQU 8BA8h
ACTION      EQU 0AB54h
IN_HAND     EQU 0AB94h
WORLD       EQU 0AB4Eh      ; far ptr to the world objects, 34h bytes each
VARSPTR     EQU 838Bh       ; far ptr to the LIFE vars
INV_OK      EQU 06AEh       ; statusScreenAllowed (LIFE allow_inventory)
REDRAW      EQU 0706h       ; full redraw pending after a camera change
PLAYER_OBJ  EQU 06AAh       ; currentWorldTarget (DEFINES WORLD_NUM_PERSO)
ACTORS      EQU 8C0Eh       ; actor table, 0A0h each
CUR_ACTOR   EQU 83F7h       ; actor being processed
TIMER       EQU 0190h       ; game timer, 60 per second, in the STACK segment (the engine reads ss:[0190])

W_FLAG      EQU 0Ch         ; world record: foundFlag (the actions it offers)
W_LIFE      EQU 0Eh         ;               foundLife
A_BETA      EQU 2Ah         ; actor fields
A_ANIM      EQU 3Eh
A_ROT       EQU 6Ah         ; RealValue: start, end, steps, start time
A_STEPS     EQU 6Eh
A_DIR       EQU 72h
A_SPEED     EQU 74h

ACTIONS_OBJ EQU 2           ; "Actions", in hand with bare hands (LIFE 561)
VAR_BARE    EQU 90          ; LIFE 561: the chosen bare-hand action
ACT_FIGHT   EQU 16
ACT_JUMP    EQU 32
ACT_OPEN    EQU 64
ACT_CLOSE   EQU 128
ACT_PUSH    EQU 256
ACT_THROW   EQU 512
ACT_DROP    EQU 1024

; ---- original segments, file-relative (Ghidra segment - 1000h); relocated ----
SEG_IRQ     EQU 1807h       ; 2807 keyboard
SEG_PLAY    EQU 032Dh       ; 132d PlayWorld
SEG_EVAL    EQU 0A8Fh       ; 1a8f evalVar, executeFoundLife, processLife
SEG_TRK     EQU 0CA6h       ; 1ca6 GereManualRot, processTrack
SEG_LIRE    EQU 0F84h       ; 1f84 Lire
SEG_FOUND   EQU 0854h       ; 1854 FoundObjet
SEG_ROT     EQU 143Eh       ; 243e InitRealValue, updateActorRotation

; ---- held-key bits (IRQ1 scan table order) ----
K_W  EQU 0001h
K_A  EQU 0002h
K_S  EQU 0004h
K_D  EQU 0008h
K_E  EQU 0010h
K_C  EQU 0020h
K_R  EQU 0040h
K_J  EQU 0080h
K_T  EQU 0100h
K_G  EQU 0200h
K_Q  EQU 0400h
K_UP EQU 0800h
K_DN EQU 1000h
K_LT EQU 2000h
K_RT EQU 4000h
NUM_SCANS   EQU 15
NUM_LETTERS EQU 11          ; the first 11 are swallowed (letters); the arrows are tracked only

H_KEY       EQU 1           ; the active control
H_MOUSE     EQU 2
H_AIM       EQU 3

TURN_TICKS  EQU 36          ; quick turn: 0.6 s at 60 Hz (ReHaunted: 15 ticks at 25 Hz)

        ORG 0
start:
entry_irq:      jmp     irq
entry_play:     jmp     play
entry_kin:      jmp     kin
entry_rot:      jmp     rot
entry_fwd:      jmp     fwd
entry_lire:     jmp     lire
entry_found:    jmp     found
entry_pic:      jmp     pic

; =============================================================================================
; IRQ1 2807:01d8 (AH = AL = raw scan code, break bit 80h; DS = game; BX CX DI free)
; Tracks the keys; W/A/S/D set the direction bits like the arrows; the letters are kept from
; the game (S would toggle the sound) unless a save name is being typed.
; =============================================================================================
irq:
        mov     bl, ah
        and     bl, 7Fh
        xor     di, di
irq_find:
        cmp     bl, byte ptr cs:[di + (scantab - start)]
        je      irq_ours
        inc     di
        cmp     di, NUM_SCANS
        jb      irq_find
        jmp     short irq_orig
irq_ours:
        mov     cx, di
        mov     bx, 1
        shl     bx, cl
        test    ah, 80h
        jnz     irq_break
        test    word ptr cs:[v_keys - start], bx
        jnz     irq_held                        ; typematic repeat: not a new press
        or      word ptr cs:[v_pressed - start], bx
irq_held:
        or      word ptr cs:[v_keys - start], bx
        jmp     short irq_dirs
irq_break:
        not     bx
        and     word ptr cs:[v_keys - start], bx
irq_dirs:
        cmp     byte ptr ds:[TO_BIOS], 0
        jne     irq_orig                        ; typing a save name: the key goes through, no
                                                ; directions (up/down would leave the name field)
        cmp     di, 3
        ja      irq_nodir
        push    ax
        mov     bx, word ptr cs:[v_keys - start]
        call    dirs_of
        mov     bl, byte ptr ds:[RAW_JOYD]
        and     bl, 0F0h
        or      bl, al
        mov     byte ptr ds:[RAW_JOYD], bl
        pop     ax
irq_nodir:
        cmp     di, NUM_LETTERS
        jae     irq_orig                        ; an arrow: the game's own handling
        db      0EAh                            ; jmp far 2807:023d, the exit (EOI, iret)
        dw      023Dh
reloc_irq_exit:
        dw      SEG_IRQ
irq_orig:
        test    word ptr ds:[LAYOUT], 0FFFFh    ; displaced
        db      0EAh
        dw      01DEh
reloc_irq_back:
        dw      SEG_IRQ

; AX = direction bits (1 up, 2 down, 4 left, 8 right) for the keys in BX
dirs_of:
        xor     ax, ax
        test    bx, K_W or K_UP
        jz      do_1
        or      al, 1
do_1:   test    bx, K_S or K_DN
        jz      do_2
        or      al, 2
do_2:   test    bx, K_A or K_LT
        jz      do_3
        or      al, 4
do_3:   test    bx, K_D or K_RT
        jz      do_4
        or      al, 8
do_4:   ret

; =============================================================================================
; PlayWorld 132d:0096, once per gameplay frame, after the input copy (DI = allowSystemMenu)
; =============================================================================================
play:
        push    ax
        push    bx
        push    cx
        push    dx
        push    si
        push    es
        inc     word ptr cs:[v_frame - start]
        call    poll_mouse
        mov     word ptr cs:[v_btnfresh - start], ax
        mov     word ptr cs:[v_btn - start], bx
        cli                                     ; presses since the last frame (IRQ1 adds)
        mov     bx, word ptr cs:[v_pressed - start]
        mov     word ptr cs:[v_pressed - start], 0
        sti
        mov     word ptr cs:[v_keyfresh - start], bx
        test    bx, K_Q
        jz      p_noq
        mov     ax, word ptr cs:[v_frame - start]
        mov     word ptr cs:[v_qframe - start], ax
p_noq:
        ; W/A/S/D in the local directions too (releasing an arrow clears the raw bits)
        mov     bx, word ptr cs:[v_keys - start]
        and     bx, K_W or K_A or K_S or K_D
        call    dirs_of
        or      word ptr ds:[LOC_JOYD], ax
        call    controls
        pop     es
        pop     si
        pop     dx
        pop     cx
        pop     bx
        pop     ax
        cmp     word ptr ds:[LOC_KEY], 0        ; displaced
        db      0EAh
        dw      009Bh
reloc_play_back:
        dw      SEG_PLAY

; AX = buttons pressed since the last poll, BX = buttons held (bit 0 left, bit 1 right).
; INT 33h AX=5 counts presses between polls, so short clicks are not lost.
poll_mouse:
        push    cx
        push    dx
        push    si
        cmp     byte ptr cs:[v_mouse - start], 0
        jne     pm_known
        xor     ax, ax                          ; reset: AX = FFFFh when a driver exists
        int     33h
        mov     byte ptr cs:[v_mouse - start], 2
        cmp     ax, 0FFFFh
        jne     pm_known
        mov     byte ptr cs:[v_mouse - start], 1
pm_known:
        xor     si, si                          ; fresh presses
        xor     bx, bx
        cmp     byte ptr cs:[v_mouse - start], 1
        jne     pm_done
        mov     ax, 5
        xor     bx, bx                          ; left
        int     33h
        or      bx, bx
        jz      pm_r
        or      si, 1
pm_r:   mov     ax, 5
        mov     bx, 1                           ; right
        int     33h
        or      bx, bx
        jz      pm_held
        or      si, 2
pm_held:
        mov     ax, 3
        int     33h
        and     bx, 3
pm_done:
        mov     ax, si
        pop     si
        pop     dx
        pop     cx
        ret

; ---- the controls (DI = allowSystemMenu, must stay; AX BX CX DX SI ES free) ----
controls:
        or      di, di                          ; where the inventory and the action key work
        jz      c_off
        cmp     word ptr ds:[INV_OK], 0
        jne     c_on
c_off:
        call    end_hold
        ret
c_on:
        mov     al, byte ptr cs:[v_hold - start]
        cmp     al, H_KEY
        je      c_key
        cmp     al, H_MOUSE
        je      c_mouse
        cmp     al, H_AIM
        je      c_aim
        jmp     c_start
c_key:
        mov     ax, word ptr cs:[v_keys - start]
        test    ax, word ptr cs:[v_holdkey - start]
        jnz     c_hold
        call    end_hold
        jmp     c_start
c_mouse:
        mov     bx, word ptr cs:[v_btn - start]
        or      bx, bx
        jnz     c_mouse_dir
        call    end_hold
        jmp     c_start
c_mouse_dir:
        call    click_dir
        mov     word ptr cs:[v_forced - start], ax
        jmp     c_hold
c_aim:
        test    word ptr cs:[v_btn - start], 2
        jz      c_aim_end
        call    hand_life
        cmp     ax, word ptr cs:[v_aimlife - start]
        jne     c_aim_end
        call    aim_update
        jmp     c_hold
c_aim_end:
        call    end_hold
        jmp     c_start
c_hold:
        mov     word ptr ds:[LOC_CLICK], 1      ; the action key, held
c_start_ret:
        ret

c_start:                                        ; a new control: one at a time, on a fresh press
        cmp     word ptr ds:[LOC_CLICK], 0      ; Space held
        jne     c_start_ret
        cmp     word ptr ds:[REDRAW], 0         ; the frame after a camera change (keys ignored)
        jne     c_start_ret
        mov     bx, word ptr cs:[v_keyfresh - start]
        mov     si, (holdtab - start)
c_keyloop:                                      ; E / C / R / J
        mov     ax, word ptr cs:[si]
        or      ax, ax
        jz      c_tg
        test    bx, ax
        jz      c_keynext
        mov     cx, ax
        mov     ax, word ptr cs:[si + 2]
        call    choose_bare
        jc      c_keynext                       ; not offered now
        mov     byte ptr cs:[v_hold - start], H_KEY
        mov     word ptr cs:[v_holdkey - start], cx
        mov     word ptr cs:[v_forced - start], -1
        jmp     c_hold
c_keynext:
        add     si, 4
        jmp     c_keyloop
c_tg:                                           ; T / G: once, on the held item
        mov     ax, ACT_THROW
        test    bx, K_T
        jnz     c_tg_do
        mov     ax, ACT_DROP
        test    bx, K_G
        jz      c_click
c_tg_do:
        call    use_held
        ret
c_click:
        mov     bx, word ptr cs:[v_btnfresh - start]
        or      bx, bx
        jz      c_ret
        call    hand_life
        mov     cx, ax
        mov     si, (aimtab - start)
c_aimfind:
        mov     ax, word ptr cs:[si]
        cmp     ax, -1
        je      c_melee
        cmp     ax, cx
        je      c_aimed
        add     si, 2
        jmp     c_aimfind
c_aimed:                                        ; gun or bow: right raises it, left alone nothing
        test    bx, 2
        jz      c_ret
        mov     word ptr cs:[v_aimlife - start], cx
        mov     byte ptr cs:[v_hold - start], H_AIM
        call    aim_update
        jmp     c_hold
c_melee:
        cmp     word ptr ds:[IN_HAND], ACTIONS_OBJ
        jne     c_melee_go                      ; a weapon: its own attacks
        mov     ax, ACT_FIGHT                   ; bare hands: Fight, as in the menu
        call    choose_bare
        jc      c_ret
c_melee_go:
        mov     byte ptr cs:[v_hold - start], H_MOUSE
        mov     bx, word ptr cs:[v_btn - start]
        call    click_dir
        mov     word ptr cs:[v_forced - start], ax
        jmp     c_hold
c_ret:
        ret

end_hold:
        mov     byte ptr cs:[v_hold - start], 0
        mov     word ptr cs:[v_forced - start], -1
        ret

; AX = keyboard_input for the held buttons in BX: left 8 (Ctrl 4), right 1 (Ctrl 2)
click_dir:
        test    byte ptr ds:[MODIFIERS], 4
        jnz     cd_ctrl
        mov     ax, 8
        test    bx, 1
        jnz     cd_ret
        mov     ax, 1
        ret
cd_ctrl:
        mov     ax, 4
        test    bx, 1
        jnz     cd_ret
        mov     ax, 2
cd_ret: ret

; ES:BX = world record of object AX (AX lost)
world_rec:
        imul    ax, ax, 34h
        les     bx, dword ptr ds:[WORLD]
        add     bx, ax
        ret

; AX = foundLife of the item in hand (-1: none)
hand_life:
        push    bx
        push    es
        mov     ax, word ptr ds:[IN_HAND]
        or      ax, ax
        js      hl_none
        call    world_rec
        mov     ax, word ptr es:[bx + W_LIFE]
        jmp     short hl_ret
hl_none:
        mov     ax, -1
hl_ret: pop     es
        pop     bx
        ret

; The inventory's choice: action AX on object DX (executeFoundLife 1a8f:1fe0). AX BX CX DX ES lost.
exec_found:
        mov     word ptr ds:[ACTION], ax
        push    dx
        db      9Ah
        dw      1FE0h
reloc_exec:
        dw      SEG_EVAL
        add     sp, 2
        mov     word ptr ds:[ACTION], 0
        ret

; Bare hands: choose Actions entry AX unless it is already the chosen one. CF = not offered.
; BX CX SI kept.
choose_bare:
        push    bx
        push    cx
        mov     cx, ax
        mov     ax, ACTIONS_OBJ
        call    world_rec
        test    word ptr es:[bx + W_FLAG], cx
        jz      cb_no
        cmp     word ptr ds:[IN_HAND], ACTIONS_OBJ
        jne     cb_do
        les     bx, dword ptr ds:[VARSPTR]
        cmp     word ptr es:[bx + 2 * VAR_BARE], cx
        je      cb_ok
cb_do:
        mov     ax, cx
        mov     dx, ACTIONS_OBJ
        call    exec_found
cb_ok:
        pop     cx
        pop     bx
        clc
        ret
cb_no:
        pop     cx
        pop     bx
        stc
        ret

; Throw / Drop (AX) the held item when it offers it
use_held:
        mov     cx, ax
        mov     ax, word ptr ds:[IN_HAND]
        cmp     ax, ACTIONS_OBJ
        je      uh_ret
        or      ax, ax
        js      uh_ret
        mov     dx, ax
        call    world_rec
        test    word ptr es:[bx + W_FLAG], cx
        jz      uh_ret
        mov     ax, cx
        call    exec_found
uh_ret: ret

; BX = DS offset of the player's actor; CF: none. AX ES kept.
player_actor:
        push    ax
        push    es
        mov     ax, word ptr ds:[PLAYER_OBJ]
        or      ax, ax
        js      pa_none
        call    world_rec
        mov     ax, word ptr es:[bx]            ; its actor index
        or      ax, ax
        js      pa_none
        imul    bx, ax, 0A0h
        add     bx, ACTORS
        pop     es
        pop     ax
        clc
        ret
pa_none:
        pop     es
        pop     ax
        stc
        ret

; Aiming (right held): left held = up held (keyboard_input 1), as Space + up on the keyboard.
; The script fires each time the aim / draw animation ends with it set, so holding left during
; the raise fires as soon as the weapon is up and keeps firing while it is held.
aim_update:
        xor     ax, ax
        test    word ptr cs:[v_btn - start], 1
        jz      au_store
        inc     ax
au_store:
        mov     word ptr cs:[v_forced - start], ax
        ret

; =============================================================================================
; keyboard_input 1a8f:03ee (evalVar case; returns with pop si / leave / retf)
; =============================================================================================
kin:
        cmp     byte ptr cs:[v_hold - start], 0
        je      kin_orig
        mov     ax, word ptr cs:[v_forced - start]
        cmp     ax, -1
        je      kin_orig
        pop     si
        leave
        retf
kin_orig:
        test    word ptr ds:[LOC_JOYD], 4       ; displaced
        db      0EAh
        dw      03F4h
reloc_kin_back:
        dw      SEG_EVAL

; =============================================================================================
; GereManualRot 1ca6:0053 (after push bp / mov bp,sp / push si / mov si,[bp+6]; returns with
; pop si / leave / retf). The quick turn: one exact half-turn per Q press for the player.
; =============================================================================================
rot:
        push    ax
        push    bx
        push    es
        mov     ax, word ptr ds:[CUR_ACTOR]
        cmp     ax, word ptr cs:[v_turnactor - start]
        jne     rot_maystart
        mov     bx, word ptr cs:[v_frame - start]
        sub     bx, word ptr cs:[v_turnlast - start]
        cmp     bx, 1
        ja      rot_cancel                      ; not updated last frame: the game took over
        mov     bx, word ptr cs:[v_frame - start]
        mov     word ptr cs:[v_turnlast - start], bx
        imul    bx, ax, 0A0h
        add     bx, ACTORS
        call    turn_step
        jmp     short rot_return
rot_cancel:
        mov     word ptr cs:[v_turnactor - start], -1
rot_maystart:
        mov     bx, word ptr cs:[v_qframe - start]
        cmp     bx, word ptr cs:[v_frame - start]
        jne     rot_orig
        call    player_actor
        jc      rot_orig
        imul    ax, word ptr ds:[CUR_ACTOR], 0A0h
        add     ax, ACTORS
        cmp     ax, bx
        jne     rot_orig                        ; not the player
        mov     word ptr ds:[bx + A_SPEED], 0   ; walking or running: he stops for the turn and,
                                                ; with W/S still held, walks on afterwards
        mov     word ptr cs:[v_qframe - start], -1
        mov     ax, word ptr ds:[bx + A_BETA]
        add     ax, 200h
        and     ax, 3FFh
        mov     word ptr cs:[v_turnend - start], ax
        push    bx
        push    ds                              ; InitRealValue(beta, end, ticks, &rotate)
        lea     ax, [bx + A_ROT]
        push    ax
        push    TURN_TICKS
        push    word ptr cs:[v_turnend - start]
        push    word ptr ds:[bx + A_BETA]
        db      9Ah
        dw      0005h
reloc_initrv:
        dw      SEG_ROT
        add     sp, 10
        pop     bx
        mov     word ptr ds:[bx + A_DIR], 2
        mov     ax, word ptr ds:[CUR_ACTOR]
        mov     word ptr cs:[v_turnactor - start], ax
        mov     ax, word ptr cs:[v_frame - start]
        mov     word ptr cs:[v_turnlast - start], ax
        call    turn_step
rot_return:
        pop     es
        pop     bx
        pop     ax
        pop     si
        leave
        retf
rot_orig:
        pop     es
        pop     bx
        pop     ax
        test    word ptr ds:[LOC_JOYD], 4       ; displaced
        db      0EAh
        dw      0059h
reloc_rot_back:
        dw      SEG_TRK

; one step of the turn for the actor at DS:BX; ends exactly on the target angle
turn_step:
        push    bx
        push    ds                              ; beta = updateActorRotation(&rotate)
        lea     ax, [bx + A_ROT]
        push    ax
        db      9Ah
        dw      0082h
reloc_updrv:
        dw      SEG_ROT
        add     sp, 4
        pop     bx
        mov     word ptr ds:[bx + A_BETA], ax
        cmp     word ptr ds:[bx + A_STEPS], 0
        jne     ts_ret
        mov     ax, word ptr cs:[v_turnend - start]
        mov     word ptr ds:[bx + A_BETA], ax
        mov     word ptr cs:[v_turnactor - start], -1
ts_ret: ret

; =============================================================================================
; Manual forward 1ca6:01c3 (processTrack, trackMode 1): no walking during the quick turn;
; Shift + forward runs.
; =============================================================================================
fwd:
        push    ax
        push    bx
        mov     ax, word ptr ds:[CUR_ACTOR]
        cmp     ax, word ptr cs:[v_turnactor - start]
        jne     fwd_run
        imul    bx, ax, 0A0h
        add     bx, ACTORS
        mov     word ptr ds:[bx + A_SPEED], 0
        pop     bx
        pop     ax
        db      0EAh                            ; jmp far 1ca6:0d0e, after the manual branch
        dw      0D0Eh
reloc_fwd_end:
        dw      SEG_TRK
fwd_run:
        test    word ptr ds:[LOC_JOYD], 1
        jz      fwd_orig
        test    byte ptr ds:[MODIFIERS], 2
        jz      fwd_orig
        imul    bx, ax, 0A0h
        add     bx, ACTORS
        cmp     word ptr ds:[bx + A_SPEED], 0
        jl      fwd_orig                        ; backing: the original handles it
        mov     word ptr ds:[bx + A_SPEED], 5   ; run
        pop     bx
        pop     ax
        db      0EAh                            ; jmp far 1ca6:0223, where forward rejoins
        dw      0223h
reloc_fwd_run:
        dw      SEG_TRK
fwd_orig:
        pop     bx
        pop     ax
        test    word ptr ds:[LOC_JOYD], 1       ; displaced
        db      0EAh
        dw      01C9h
reloc_fwd_back:
        dw      SEG_TRK

; =============================================================================================
; Screens: a fresh left click
; =============================================================================================
lire:                                           ; 1f84:0fa5: as Enter (next page; the last closes)
        push    ax
        push    bx
        call    poll_mouse
        test    ax, 1
        jz      lire_orig
        mov     word ptr ds:[LOC_KEY], 1Ch
lire_orig:
        pop     bx
        pop     ax
        cmp     word ptr ds:[LOC_KEY], 1        ; displaced
        db      0EAh
        dw      0FAAh
reloc_lire_back:
        dw      SEG_LIRE

found:                                          ; 1854:047f: as the action key (confirm)
        push    ax
        push    bx
        call    poll_mouse
        test    ax, 1
        jz      found_orig
        mov     word ptr ds:[LOC_CLICK], 1
found_orig:
        pop     bx
        pop     ax
        cmp     word ptr ds:[ANTIREBOND], 0     ; displaced
        db      0EAh
        dw      0484h
reloc_found_back:
        dw      SEG_FOUND

pic:                                            ; 1a8f:1b92: closes the picture
        push    ax
        push    bx
        call    poll_mouse
        test    ax, 1
        pop     bx
        pop     ax
        jz      pic_orig
        db      0EAh                            ; jmp far 1a8f:1b99, the Click exit
        dw      1B99h
reloc_pic_exit:
        dw      SEG_EVAL
pic_orig:
        cmp     word ptr ds:[RAW_CLICK], 0      ; displaced
        db      0EAh
        dw      1B97h
reloc_pic_back:
        dw      SEG_EVAL

; ---- tables ----
scantab db      11h, 1Eh, 1Fh, 20h, 12h, 2Eh, 13h, 24h, 14h, 22h, 10h   ; W A S D E C R J T G Q
        db      48h, 50h, 4Bh, 4Dh                                      ; up down left right
holdtab dw      K_E, ACT_OPEN, K_C, ACT_CLOSE, K_R, ACT_PUSH, K_J, ACT_JUMP, 0
        ; the aimed weapons' foundLife: rifle, revolver, bow
aimtab  dw      12, 365, 29, -1

; ---- state ----
v_keys      dw  0           ; keys held (IRQ1)
v_pressed   dw  0           ; keys pressed since the last frame (IRQ1 sets, PlayWorld clears)
v_keyfresh  dw  0
v_btn       dw  0           ; mouse buttons held / pressed this frame
v_btnfresh  dw  0
v_frame     dw  0
v_qframe    dw  -1          ; frame of the last Q press
v_hold      db  0           ; the active control (H_*)
v_mouse     db  0           ; 0 unknown, 1 driver, 2 none
v_holdkey   dw  0
v_forced    dw  -1          ; keyboard_input while a control holds the action key
v_aimlife   dw  0
v_turnactor dw  -1
v_turnend   dw  0
v_turnlast  dw  0

CTRL    ENDS
        END
