// Protect the King - 2D. Player-controlled guard tier.

#include "Characters/PTKGuardCharacter.h"

#include "AI/PTKGuardAIController.h"
#include "Combat/PTKCombatTarget.h"

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

void APTKGuardCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ConstrainToWalkableGround();
}

void APTKGuardCharacter::ConstrainToWalkableGround()
{
	const APTKBattlefield* Field = APTKBattlefield::Get(GetWorld());
	if (!Field || IsDead())
	{
		return;
	}

	const FVector Now = GetActorLocation();

	if (Field->IsWalkable(Now))
	{
		LastWalkablePosition = Now;
		bHasWalkableAnchor = true;
		return;
	}

	// No anchor yet means the guard has been off-road since it existed - placed
	// or spawned somewhere blocked. Put it on the nearest road rather than
	// leaving it stuck where it cannot legally move.
	if (!bHasWalkableAnchor)
	{
		SetActorLocation(Field->FindNearestWalkable(Now));
		LastWalkablePosition = GetActorLocation();
		bHasWalkableAnchor = true;
		return;
	}

	// Slide: keep whichever single axis of the attempted move stays legal.
	const FVector SlideX(Now.X, Now.Y, LastWalkablePosition.Z);
	const FVector SlideZ(LastWalkablePosition.X, Now.Y, Now.Z);

	if (Field->IsWalkable(SlideX))
	{
		SetActorLocation(SlideX);
	}
	else if (Field->IsWalkable(SlideZ))
	{
		SetActorLocation(SlideZ);
	}
	else
	{
		SetActorLocation(FVector(LastWalkablePosition.X, Now.Y, LastWalkablePosition.Z));
	}
	LastWalkablePosition = GetActorLocation();
}

bool APTKGuardCharacter::GetProjectileAim(FVector& OutAim) const
{
	const APTKGuardAIController* AI = Cast<APTKGuardAIController>(GetController());
	if (!AI) return Super::GetProjectileAim(OutAim);

	const AActor* Target = AI->GetTarget();
	if (!PTKCombat::IsHostileTarget(this, Target)) return false;

	FVector Offset = Target->GetActorLocation() - GetActorLocation();
	Offset.Y = 0.0f;
	if (Offset.IsNearlyZero() || Offset.Size() > GetAttackReach()) return false;

	// Aim at release, after the wind-up. Lead steady movement so an enemy
	// crossing the lane does not step out of the flight path before arrival.
	FVector Velocity = Target->GetVelocity();
	Velocity.Y = 0.0f;
	const double A = Velocity.SizeSquared() - FMath::Square(ProjectileSpeed);
	const double B = 2.0 * FVector::DotProduct(Offset, Velocity);
	const double C = Offset.SizeSquared();
	double FlightTime = -1.0;
	if (FMath::Abs(A) < KINDA_SMALL_NUMBER)
	{
		if (B < -KINDA_SMALL_NUMBER) FlightTime = -C / B;
	}
	else
	{
		const double Discriminant = B * B - 4.0 * A * C;
		if (Discriminant >= 0.0)
		{
			const double Root = FMath::Sqrt(Discriminant);
			const double T1 = (-B - Root) / (2.0 * A);
			const double T2 = (-B + Root) / (2.0 * A);
			FlightTime = T1 > 0.0 ? T1 : T2;
			if (T2 > 0.0 && T2 < FlightTime) FlightTime = T2;
		}
	}
	if (FlightTime > 0.0 && FlightTime * ProjectileSpeed <= GetAttackReach())
	{
		Offset += Velocity * FlightTime;
	}
	OutAim = Offset.GetSafeNormal();
	return true;
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
