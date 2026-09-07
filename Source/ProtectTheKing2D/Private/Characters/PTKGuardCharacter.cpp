// Protect the King - 2D. Player-controlled guard tier.

#include "Characters/PTKGuardCharacter.h"

#include "Components/PTKHealthComponent.h"
#include "Core/PTKBattlefield.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGuardCharacter)

APTKGuardCharacter::APTKGuardCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// Guards are the characters the player drives, so they own the view.
	bEnableCameraRig = true;

	// Melee only damages the opposing team, which is what will stop a guard's
	// swing from hitting the King he is defending once the King exists.
	Team = EPTKTeam::Guards;

	// GUARD SCALE. A guard is meant to stand against a crowd of enemies, not
	// to trade evenly with one of them, so guard health is roughly two orders
	// of magnitude above a single enemy's. Per-guard Blueprints override this;
	// it is the tier default so a new guard is durable without remembering to
	// set anything.
	if (HealthComponent)
	{
		HealthComponent->SetMaxHealth(7000.0f);
	}

	// RANGE ADVANTAGE. A guard strikes from 3.5 tiles, an enemy from 1.0, so a
	// guard gets 2.5 tiles of reach the enemy has to cross under fire. This is
	// the single most important balance relationship in the prototype, and it
	// is stated in tiles rather than world units so it survives any change to
	// the map scale.
	AttackRangeTiles = 3.5f;

	// A wide arc: the axe is a sweeping weapon and should catch several
	// attackers standing shoulder to shoulder in front of it.
	AttackHitWidthFactor = 0.5f;

	AttackDamage = 25.0f;

	// Facing the camera reads best for a character standing on a spawn pad.
	DefaultFacingDirection = EPTKFacingDirection::Down;
}

void APTKGuardCharacter::PostInitializeComponents()
{
	// BEFORE Super, and not in BeginPlay, because Super is where APawn spawns
	// the default AI controller for a placed guard - and that controller reads
	// HomePosition the moment it possesses. Capturing the post in BeginPlay
	// left every AI guard believing its post was the world origin, so all four
	// tried to defend the same spot.
	CaptureHomePosition();
	Super::PostInitializeComponents();
}

void APTKGuardCharacter::BeginPlay()
{
	Super::BeginPlay();

	// Again for a guard SPAWNED at runtime, whose transform may not have been
	// final when PostInitializeComponents ran.
	CaptureHomePosition();

	if (APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Field->RegisterGuard(this);
	}
}

void APTKGuardCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
	if (APTKBattlefield* Field = APTKBattlefield::Get(GetWorld()))
	{
		Field->UnregisterGuard(this);
	}
	Super::EndPlay(Reason);
}

void APTKGuardCharacter::CaptureHomePosition()
{
	// Where the guard stands IS its post, so a designer sets it by dragging the
	// actor. An explicitly authored HomePosition is left alone.
	if (HomePosition.IsNearlyZero())
	{
		HomePosition = GetActorLocation();
	}
}
