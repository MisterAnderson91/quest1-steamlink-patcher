# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Gregory Anderson
#
# Subclass of Steam Link's 2D activity, added to the app as classes2.dex
# (the manifest's launcher activity is renamed to this class). When Steam
# Link starts its VR activity, launch it on display 0: on the Quest 1 it
# would otherwise stay on the 2D panel's virtual display and never get the
# screen. Valve's own code is left unchanged.
.class public Lcom/valvesoftware/steamlink/SteamLinkQ1;
.super Lcom/valvesoftware/steamlink/SteamLink;
.source "SteamLinkQ1.java"


.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Lcom/valvesoftware/steamlink/SteamLink;-><init>()V

    return-void
.end method

.method public startActivity(Landroid/content/Intent;)V
    .locals 2

    invoke-virtual {p1}, Landroid/content/Intent;->getComponent()Landroid/content/ComponentName;

    move-result-object v0

    if-eqz v0, :plain

    invoke-virtual {v0}, Landroid/content/ComponentName;->getClassName()Ljava/lang/String;

    move-result-object v0

    const-string v1, "com.valvesoftware.steamlink.VRLink"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-eqz v0, :plain

    const-string v0, "SteamLinkQ1"

    const-string v1, "startActivity: launching VRLink on display 0"

    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    invoke-static {}, Landroid/app/ActivityOptions;->makeBasic()Landroid/app/ActivityOptions;

    move-result-object v0

    const/4 v1, 0x0

    invoke-virtual {v0, v1}, Landroid/app/ActivityOptions;->setLaunchDisplayId(I)Landroid/app/ActivityOptions;

    move-result-object v0

    invoke-virtual {v0}, Landroid/app/ActivityOptions;->toBundle()Landroid/os/Bundle;

    move-result-object v0

    invoke-virtual {p0, p1, v0}, Lcom/valvesoftware/steamlink/SteamLinkQ1;->startActivity(Landroid/content/Intent;Landroid/os/Bundle;)V

    return-void

    :plain
    invoke-super {p0, p1}, Lcom/valvesoftware/steamlink/SteamLink;->startActivity(Landroid/content/Intent;)V

    return-void
.end method
