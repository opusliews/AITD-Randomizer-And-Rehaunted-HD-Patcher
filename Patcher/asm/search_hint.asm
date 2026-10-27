; Search hint for INDARK.EXE (GOG): an outlined "?" near the bottom right of the screen while
; the player is near a type-9 hard-collision zone (the searchable zones), like ReHaunted's
; magnifier (TatouSource/FitdLib/mainLoop.cpp detectNearbyInteractiveHotspot).
;
; Appended to the exe as a new segment (vanilla_exe.py --search-hint); entered by a far jump
; from the epilogue of the text overlay 1f84:0451 (FITD drawTextOverlay), which every redraw
; calls before adding its box to the redraw list (15c4:012d). Runs in that function's frame:
;   SI = its return value (1 = text drawn, the caller adds BBox3D to the redraw boxes),
;        kept in its dead local [bp-6]; [bp-2]/[bp-4] hold the player's centre x/z
;   DI = top y of the messages (stored to BBox3D2)
; Addresses (Research/VanillaExe_Ghidra.md):
;   DS:06C2 lightOff        DS:06AC camera-target actor   DS:8C0E actor table, 0A0h each
;   actor +08..+12 ZV x1,x2,y1,y2,z1,z2   +30 room
;   DS:06F2 far ptr to the room table (far ptr per room); room +[0] -> hard-col list:
;           count, then 16-byte records x1,x2,y1,y2,z1,z2,parameter,type
;   DS:62FB/62FD/62FF/6301 BBox3D x1,y1,x2,y2   DS:88A0 font   DS:7C8E logical screen
;   2770:011D SetFont(font far, colour)   2770:0012 PrintFont(x, y, screen far, text far)
; The two far-call segments and the hook's segment are relocated (vanilla_exe.py adds the
; relocation entries).

        ; no CPU directive (ML 14 rejects .186/.286): vanilla_exe.py rejects 386 encodings
HINT    SEGMENT USE16 PUBLIC 'CODE'
        ASSUME  CS:HINT, DS:NOTHING, ES:NOTHING

MARGIN  EQU 1000                ; Manhattan distance (XZ), as ReHaunted
HX      EQU 303                 ; glyph cell origin; '?' ink is columns 1-7, rows 2-14
HY      EQU 170
BLACK   EQU 0
TEXTCOL EQU 16                  ; the message colour

        ORG 0
start:
        mov     word ptr ds:[62FDh], di         ; displaced: BBox3D2 = top of the messages
        mov     [bp-6], si                      ; the return value (the locals are dead here)
        jmp     short begin
done:
        mov     ax, [bp-6]
        pop     di
        pop     si
        leave
        retf
begin:
        cmp     word ptr ds:[06C2h], 0          ; dark room: no hint
        jne     done
        mov     bx, word ptr ds:[06ACh]
        or      bx, bx
        js      done
        imul    bx, bx, 0A0h
        add     bx, 8C0Eh                       ; DS:BX = player actor
        mov     ax, [bx+08h]
        add     ax, [bx+0Ah]
        sar     ax, 1
        mov     [bp-2], ax                      ; centre x
        mov     ax, [bx+10h]
        add     ax, [bx+12h]
        sar     ax, 1
        mov     [bp-4], ax                      ; centre z
        mov     ax, [bx+30h]                    ; room
        or      ax, ax
        js      done
        shl     ax, 2
        les     bx, dword ptr ds:[06F2h]
        add     bx, ax
        les     bx, dword ptr es:[bx]           ; ES:BX = room data
        add     bx, es:[bx]                     ; hard-col list
        mov     cx, es:[bx]
        add     bx, 2
        jcxz    done
zone:
        cmp     word ptr es:[bx+0Eh], 9
        jne     next
        mov     ax, [bp-2]                      ; x distance to the box (0 inside)
        mov     dx, es:[bx]
        sub     dx, ax                          ; x1 - cx
        jg      xok
        sub     ax, es:[bx+2]                   ; cx - x2
        mov     dx, ax
        jg      xok
        xor     dx, dx
xok:
        cmp     dx, MARGIN
        jge     next
        mov     ax, [bp-4]                      ; z distance
        mov     si, es:[bx+8]
        sub     si, ax                          ; z1 - cz
        jg      zok
        sub     ax, es:[bx+0Ah]                 ; cz - z2
        mov     si, ax
        jg      zok
        xor     si, si
zok:
        add     dx, si
        cmp     dx, MARGIN
        jl      hit
next:
        add     bx, 10h
        loop    zone
        jmp     done
hit:
        mov     ax, BLACK
        call    setfont
        mov     si, outline - start            ; constants: no linker fixups
oloop:
        mov     al, cs:[si+1]
        cbw
        add     ax, HY
        mov     dx, ax
        mov     al, cs:[si]
        cbw
        add     ax, HX
        call    print
        add     si, 2
        cmp     si, outline_end - start
        jb      oloop
        mov     ax, TEXTCOL
        call    setfont
        mov     ax, HX
        mov     dx, HY
        call    print
        mov     word ptr [bp-6], 1              ; text drawn: the caller adds the box
        mov     ax, HX - 1
        cmp     ax, word ptr ds:[62FBh]
        jge     b1
        mov     word ptr ds:[62FBh], ax
b1:     mov     ax, HX + 9
        cmp     ax, word ptr ds:[62FFh]
        jle     b2
        mov     word ptr ds:[62FFh], ax
b2:     mov     ax, HY
        cmp     ax, word ptr ds:[62FDh]
        jge     fin
        mov     word ptr ds:[62FDh], ax
fin:    jmp     done

print:                                          ; AX = x, DX = y
        push    cs
        mov     bx, qmark - start               ; (a push of the constant would be 32-bit)
        push    bx
        push    word ptr ds:[7C90h]
        push    word ptr ds:[7C8Eh]
        push    dx
        push    ax
        db      9Ah                             ; call far 2770:0012 PrintFont
        dw      0012h
printseg dw     0
        add     sp, 0Ch
        ret

setfont:                                        ; AX = colour
        push    ax
        push    word ptr ds:[88A2h]
        push    word ptr ds:[88A0h]
        db      9Ah                             ; call far 2770:011D SetFont
        dw      011Dh
fontseg dw      0
        add     sp, 6
        ret

outline db      -1,-1, 0,-1, 1,-1, -1,0, 1,0, -1,1, 0,1, 1,1
outline_end:
qmark   db      '?', 0

HINT    ENDS
        END
